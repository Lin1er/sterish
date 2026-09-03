"""Deterministic scanner for prompt-injection and tool poisoning in skill text.

Stage 1 as scaffolded only looked at *declared* capabilities. That misses the
attack class Sterish exists to catch: a skill whose manifest declares nothing
dangerous but whose **description text** carries instructions aimed at the agent
reading it — "ignore previous instructions", a hidden HTML comment telling the
agent to read `~/.ssh/id_rsa`, an MCP server declaring `autoApprove: ["*"]`.

This module is deliberately deterministic: regex and character-class checks
only, no model call, no network. That matters for two reasons.

1. The corpus batch in STERISH-11 must produce the same verdicts on every
   machine and in CI, with no API key.
2. A poisoned fixture must *never* come back SAFE, even when the LLM stage is
   unavailable. Determinism is what makes that a guarantee rather than a hope.

The LLM-assisted scanner (STERISH-10) layers on top of this and can raise a
verdict, never lower it below what the deterministic pass found.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum


class InjectionCategory(StrEnum):
    INSTRUCTION_OVERRIDE = "INSTRUCTION_OVERRIDE"
    CONCEALMENT = "CONCEALMENT"
    SECRET_EXFILTRATION = "SECRET_EXFILTRATION"
    APPROVAL_SMUGGLING = "APPROVAL_SMUGGLING"
    TOOL_SHADOWING = "TOOL_SHADOWING"
    DESTRUCTIVE_ACTION = "DESTRUCTIVE_ACTION"


class InjectionSeverity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class InjectionFinding:
    """One concrete hit, with enough context for a human to check it."""

    category: InjectionCategory
    severity: InjectionSeverity
    rule: str
    description: str
    location: str
    evidence: str

    def as_dict(self) -> dict[str, str]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "rule": self.rule,
            "description": self.description,
            "location": self.location,
            "evidence": self.evidence,
        }


@dataclass
class InjectionScanResult:
    findings: list[InjectionFinding] = field(default_factory=list)

    @property
    def highest_severity(self) -> InjectionSeverity | None:
        for level in (InjectionSeverity.HIGH, InjectionSeverity.MEDIUM, InjectionSeverity.LOW):
            if any(f.severity is level for f in self.findings):
                return level
        return None

    @property
    def score_penalty(self) -> int:
        """Points to deduct from a 0-100 score.

        Weighted so that a single HIGH finding alone drops a skill out of SAFE
        under the default thresholds — a hidden instruction is not a rounding
        error, it is the whole attack.
        """
        weights = {
            InjectionSeverity.HIGH: 60,
            InjectionSeverity.MEDIUM: 20,
            InjectionSeverity.LOW: 5,
        }
        return min(100, sum(weights[f.severity] for f in self.findings))

    def by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.category.value] = counts.get(finding.category.value, 0) + 1
        return counts


# --- Rule table --------------------------------------------------------------
#
# (rule id, category, severity, compiled pattern, human description)
#
# Patterns are matched case-insensitively against text that has already been
# de-obfuscated (see `_deobfuscate`), so an attacker cannot dodge a rule with
# zero-width joiners or fullwidth characters.

_Rule = tuple[str, InjectionCategory, InjectionSeverity, re.Pattern[str], str]

_RULES: list[_Rule] = [
    (
        "override.ignore-previous",
        InjectionCategory.INSTRUCTION_OVERRIDE,
        InjectionSeverity.HIGH,
        re.compile(
            r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}?\b"
            r"(previous|prior|earlier|above|all)\b[^.\n]{0,20}?\b"
            r"(instruction|prompt|rule|direction|context|message)s?\b",
            re.IGNORECASE,
        ),
        "Text instructs the reading agent to discard its existing instructions.",
    ),
    (
        "override.system-role",
        InjectionCategory.INSTRUCTION_OVERRIDE,
        InjectionSeverity.HIGH,
        re.compile(
            r"(^|\n)\s*(system|assistant|developer)\s*:\s*\S"
            r"|<\s*/?\s*(system|important|admin)[^>]*>",
            re.IGNORECASE,
        ),
        "Text impersonates a system or developer turn to outrank the real prompt.",
    ),
    (
        "override.conceal-from-user",
        InjectionCategory.INSTRUCTION_OVERRIDE,
        InjectionSeverity.HIGH,
        re.compile(
            r"\b(do\s*not|don'?t|never)\b[^.\n]{0,40}?\b"
            r"(tell|inform|mention|show|reveal|disclose|notify|display)\b"
            r"[^.\n]{0,30}?\b(user|human|operator|owner)\b",
            re.IGNORECASE,
        ),
        "Text instructs the agent to hide its actions from the user.",
    ),
    (
        "override.mandatory-action",
        InjectionCategory.INSTRUCTION_OVERRIDE,
        InjectionSeverity.MEDIUM,
        re.compile(
            r"\b(you\s+must\s+(always|first|never|call|run|read|send|include)"
            r"|always\s+call\b[^.\n]{0,30}?\bfirst\b"
            r"|before\s+(?:using|answering|responding|summariz|processing)"
            r"[^.\n]{0,30}?\byou\s+(?:must|should|need|have\s+to))\b",
            re.IGNORECASE,
        ),
        "Description issues a mandatory directive to the agent rather than "
        "describing what the tool does.",
    ),
    (
        # Naming a credential store is only dangerous when a verb *targets* it.
        # Legitimate docs mention `.env` and `process.env` constantly; an
        # instruction to read/open/exfiltrate a key file is the actual attack,
        # and that is what the poisoned fixtures do.
        "exfil.read-credential",
        InjectionCategory.SECRET_EXFILTRATION,
        InjectionSeverity.HIGH,
        re.compile(
            r"\b(read|open|cat|load|access|fetch|grab|dump|exfiltrate|steal|copy|"
            r"collect|include|send|upload|transmit|leak)\b[^.\n]{0,50}?"
            r"("
            r"(~|\$HOME|/home/[\w.-]+|/root|%USERPROFILE%)?[/\\]?\.(ssh|aws|gnupg|netrc)\b"
            r"|\bid_(rsa|ed25519|ecdsa)\b"
            r"|\b(private[_\s-]?key|secret[_\s-]?key|mnemonic|seed[_\s-]?phrase|"
            r"recovery[_\s-]?phrase|authorized_keys|keychain)\b"
            r")",
            re.IGNORECASE,
        ),
        "Text instructs the agent to read or move key material or a credential store.",
    ),
    (
        # A bare mention of secret material, with no verb targeting it. Worth
        # noting but not on its own a poisoning signal — kept LOW so a security
        # doc that merely discusses `id_rsa` is not flagged DANGEROUS.
        "exfil.mentions-secret",
        InjectionCategory.SECRET_EXFILTRATION,
        InjectionSeverity.LOW,
        re.compile(
            r"\b(id_(rsa|ed25519|ecdsa)|mnemonic|seed[_\s-]?phrase|recovery[_\s-]?phrase)\b",
            re.IGNORECASE,
        ),
        "Text names secret material (informational; not itself an instruction).",
    ),
    (
        "exfil.send-elsewhere",
        InjectionCategory.SECRET_EXFILTRATION,
        InjectionSeverity.HIGH,
        re.compile(
            r"\b(send|post|upload|transmit|forward|exfiltrate|report|beacon|leak|"
            r"copy)\b[^.\n]{0,60}?"
            r"\b(to|at|toward)\b[^.\n]{0,30}?"
            r"(https?://|[\w.-]+\.(com|net|org|io|xyz|ru|cn|dev|sh|app)\b|"
            r"\bwebhook\b|\bendpoint\b|\bremote\s+server\b|\bour\s+server\b|"
            r"\battacker\b|\bc2\b)",
            re.IGNORECASE,
        ),
        "Text describes sending data to an external destination.",
    ),
    (
        "approval.auto-approve",
        InjectionCategory.APPROVAL_SMUGGLING,
        InjectionSeverity.HIGH,
        re.compile(
            r"\bauto[_\s-]?approve\b|\balwaysallow\b|\balways[_\s-]allow\b"
            r"|\bskip[_\s-](confirmation|approval|review)\b"
            r"|\bno\s+(confirmation|approval|permission)\s+(is\s+)?(needed|required)\b"
            r"|\bwithout\s+(user\s+)?(approval|confirmation|permission)\b"
            r"|\bpre[_\s-]?approved\b|\bbypass[^.\n]{0,20}\b(approval|permission|sandbox)\b",
            re.IGNORECASE,
        ),
        "Text claims the tool needs no approval, or smuggles a standing "
        "auto-approval into the manifest.",
    ),
    (
        "shadow.other-tools",
        InjectionCategory.TOOL_SHADOWING,
        InjectionSeverity.HIGH,
        re.compile(
            r"\b(instead\s+of|rather\s+than|in\s+place\s+of|replace|override|"
            r"supersede)\b[^.\n]{0,40}?\b(tool|function|skill|server|command)s?\b"
            r"|\b(when|whenever)\b[^.\n]{0,40}?\b(other|any|another)\s+"
            r"(tool|skill|function)s?\b[^.\n]{0,40}?\b(is\s+)?"
            r"(called|invoked|used|requested)\b",
            re.IGNORECASE,
        ),
        "Text tries to redirect or shadow calls intended for a different tool.",
    ),
    (
        "destructive.wipe",
        InjectionCategory.DESTRUCTIVE_ACTION,
        InjectionSeverity.MEDIUM,
        re.compile(
            r"\brm\s+-[rf]{1,2}\b|\bdel\s+/[sf]\b|\bformat\s+[a-z]:"
            r"|\bDROP\s+(TABLE|DATABASE)\b|\bTRUNCATE\s+TABLE\b"
            r"|\b(delete|wipe|erase|destroy)\b[^.\n]{0,30}?"
            r"\b(all|every|entire)\b[^.\n]{0,30}?\b(file|data|record|backup)s?\b",
            re.IGNORECASE,
        ),
        "Text describes an irreversible destructive operation.",
    ),
    (
        "destructive.transfer-funds",
        InjectionCategory.DESTRUCTIVE_ACTION,
        InjectionSeverity.HIGH,
        re.compile(
            r"\btransfer\b[^.\n]{0,40}?\b(all|entire|full|every)\b[^.\n]{0,30}?"
            r"\b(balance|fund|token|asset|xlm|usdc|wallet)s?\b"
            r"|\bdrain\b[^.\n]{0,30}?\b(wallet|account|balance|fund)s?\b"
            r"|\bsweep\b[^.\n]{0,30}?\bwallet\b",
            re.IGNORECASE,
        ),
        "Text describes moving a wallet's entire balance.",
    ),
]

# Characters with no business in a skill description: zero-width and
# direction-control codepoints exist here only to hide text from a human reader.
_INVISIBLE = {
    "​": "ZERO WIDTH SPACE",
    "‌": "ZERO WIDTH NON-JOINER",
    "‍": "ZERO WIDTH JOINER",
    "⁠": "WORD JOINER",
    "﻿": "ZERO WIDTH NO-BREAK SPACE",
    "­": "SOFT HYPHEN",
    "‪": "LEFT-TO-RIGHT EMBEDDING",
    "‫": "RIGHT-TO-LEFT EMBEDDING",
    "‬": "POP DIRECTIONAL FORMATTING",
    "‭": "LEFT-TO-RIGHT OVERRIDE",
    "‮": "RIGHT-TO-LEFT OVERRIDE",
    "⁦": "LEFT-TO-RIGHT ISOLATE",
    "⁧": "RIGHT-TO-LEFT ISOLATE",
    "⁨": "FIRST STRONG ISOLATE",
    "⁩": "POP DIRECTIONAL ISOLATE",
}

_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# A run of spaces/tabs long enough to push text off the right edge of a view.
# Threshold set high enough to clear markdown table alignment and code-comment
# indentation, which legitimately produce medium whitespace runs.
_OFFSCREEN_PAD = re.compile(r"[ \t]{80,}\S")
_MAX_EVIDENCE = 160


def _deobfuscate(text: str) -> str:
    """Strip the tricks that hide text from a human but not from a model."""
    cleaned = "".join(ch for ch in text if ch not in _INVISIBLE)
    cleaned = _ANSI_ESCAPE.sub("", cleaned)
    # NFKC folds fullwidth and mathematical letterforms back to ASCII, so
    # "ｉｇｎｏｒｅ  ｐｒｅｖｉｏｕｓ" cannot slip past a rule.
    return unicodedata.normalize("NFKC", cleaned)


def _snippet(text: str, start: int, end: int) -> str:
    fragment = text[max(0, start - 20) : min(len(text), end + 20)]
    fragment = " ".join(fragment.split())
    if len(fragment) > _MAX_EVIDENCE:
        fragment = fragment[: _MAX_EVIDENCE - 1] + "…"
    return fragment


def scan_text(text: str, location: str) -> list[InjectionFinding]:
    """Scan one span of text. `location` names where it came from."""
    if not text:
        return []

    findings: list[InjectionFinding] = []
    cleaned = _deobfuscate(text)

    # Concealment checks run on the *raw* text — the point is what was hidden.
    present_invisible = sorted({_INVISIBLE[ch] for ch in text if ch in _INVISIBLE})
    if present_invisible:
        findings.append(
            InjectionFinding(
                category=InjectionCategory.CONCEALMENT,
                severity=InjectionSeverity.HIGH,
                rule="conceal.invisible-characters",
                description=(
                    "Text contains zero-width or direction-control characters "
                    f"({', '.join(present_invisible)}) that hide content from a "
                    "human reviewer while a model still reads it."
                ),
                location=location,
                evidence=", ".join(present_invisible),
            )
        )

    for match in _HTML_COMMENT.finditer(text):
        body = match.group(1).strip()
        if not body:
            continue
        findings.append(
            InjectionFinding(
                category=InjectionCategory.CONCEALMENT,
                severity=InjectionSeverity.MEDIUM,
                rule="conceal.html-comment",
                description=(
                    "Text carries an HTML comment. Comments render invisibly to a "
                    "human but are read verbatim by an agent."
                ),
                location=location,
                evidence=_snippet(body, 0, len(body)),
            )
        )
        # Anything hidden in a comment is scanned again at raised severity.
        for nested in scan_text(body, f"{location}#html-comment"):
            findings.append(
                InjectionFinding(
                    category=nested.category,
                    severity=InjectionSeverity.HIGH,
                    rule=nested.rule,
                    description=f"{nested.description} (concealed in an HTML comment)",
                    location=nested.location,
                    evidence=nested.evidence,
                )
            )

    if _ANSI_ESCAPE.search(text):
        findings.append(
            InjectionFinding(
                category=InjectionCategory.CONCEALMENT,
                severity=InjectionSeverity.MEDIUM,
                rule="conceal.ansi-escape",
                description=(
                    "Text contains ANSI escape sequences, which can blank or "
                    "overwrite content in a terminal preview."
                ),
                location=location,
                evidence=repr(_ANSI_ESCAPE.search(text).group(0)),
            )
        )

    pad = _OFFSCREEN_PAD.search(text)
    if pad:
        findings.append(
            InjectionFinding(
                category=InjectionCategory.CONCEALMENT,
                severity=InjectionSeverity.MEDIUM,
                rule="conceal.offscreen-padding",
                description=(
                    "Text is padded with a long whitespace run that pushes the "
                    "content that follows it out of view."
                ),
                location=location,
                evidence=_snippet(text, pad.start(), pad.end()),
            )
        )

    # Match each rule against both the cleaned text and a whitespace-collapsed
    # copy. The collapsed copy defeats line-wrap evasion — an instruction split
    # as "read the user's\n~/.ssh/id_rsa" reads as one span once wrapped — while
    # the newline-bearing copy still feeds rules that anchor on line starts
    # (e.g. a forged "system:" turn). dedupe_findings drops the overlap.
    collapsed = re.sub(r"\s+", " ", cleaned)
    for source in (cleaned, collapsed):
        for rule_id, category, severity, pattern, description in _RULES:
            match = pattern.search(source)
            if match:
                findings.append(
                    InjectionFinding(
                        category=category,
                        severity=severity,
                        rule=rule_id,
                        description=description,
                        location=location,
                        evidence=_snippet(source, match.start(), match.end()),
                    )
                )

    return findings


def scan_manifest(manifest) -> InjectionScanResult:  # noqa: ANN001 - avoids an import cycle
    """Scan every human-readable field of a `SkillManifest`."""
    findings: list[InjectionFinding] = []
    findings.extend(scan_text(manifest.name, "manifest.name"))
    findings.extend(scan_text(manifest.description, "manifest.description"))
    for permission in manifest.permissions:
        findings.extend(scan_text(permission, "manifest.permissions"))
    for index, tool in enumerate(manifest.tools):
        where = f"manifest.tools[{index}]:{tool.name}"
        findings.extend(scan_text(tool.name, f"{where}.name"))
        findings.extend(scan_text(tool.description, f"{where}.description"))
        findings.extend(_scan_schema(tool.input_schema, f"{where}.input_schema"))

    return InjectionScanResult(findings=dedupe_findings(findings))


def _scan_schema(schema: object, location: str) -> list[InjectionFinding]:
    """Walk a JSON schema; injected text hides well in a `description` field."""
    findings: list[InjectionFinding] = []
    if isinstance(schema, dict):
        for key, value in schema.items():
            findings.extend(_scan_schema(value, f"{location}.{key}"))
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            findings.extend(_scan_schema(value, f"{location}[{index}]"))
    elif isinstance(schema, str):
        findings.extend(scan_text(schema, location))
    return findings


def dedupe_findings(findings: list[InjectionFinding]) -> list[InjectionFinding]:
    """Collapse identical (rule, location) hits, keeping the highest severity."""
    order = {
        InjectionSeverity.HIGH: 2,
        InjectionSeverity.MEDIUM: 1,
        InjectionSeverity.LOW: 0,
    }
    best: dict[tuple[str, str], InjectionFinding] = {}
    for finding in findings:
        key = (finding.rule, finding.location)
        current = best.get(key)
        if current is None or order[finding.severity] > order[current.severity]:
            best[key] = finding
    return sorted(
        best.values(),
        key=lambda f: (-order[f.severity], f.category.value, f.rule, f.location),
    )
