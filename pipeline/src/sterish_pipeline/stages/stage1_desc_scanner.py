"""Stage 1: Tool description and capability scanning.

Two independent signals feed the stage-1 score:

1. **Declared capabilities** — what the manifest admits it can do. A skill that
   declares WALLET_ACCESS is riskier than one that declares FILE_READ.
2. **The text itself** — what the description tries to make the reading agent
   do. This is the tool-poisoning class, and it is invisible to (1): a poisoned
   skill declares nothing and hides its payload in prose.

Signal (2) is deterministic (see `intake/injection.py`) so the corpus batch and
CI produce identical verdicts with no API key. The LLM-assisted scanner
(STERISH-10) layers on top; it may raise severity, never lower it below what
this pass found.
"""

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.intake.injection import (
    InjectionScanResult,
    dedupe_findings,
    scan_manifest,
    scan_text,
)
from sterish_pipeline.models import (
    Capability,
    InjectionFlag,
    RiskFlag,
    Severity,
    SkillManifest,
    Stage1Result,
)

# Mapping: capability -> base severity.
_CAPABILITY_SEVERITY: dict[Capability, Severity] = {
    Capability.WALLET_ACCESS: Severity.HIGH,
    Capability.SECRET_READ: Severity.HIGH,
    Capability.NETWORK_OUTBOUND: Severity.HIGH,
    Capability.FILE_WRITE: Severity.MEDIUM,
    Capability.ENV_READ: Severity.MEDIUM,
    Capability.FILE_READ: Severity.LOW,
}

_SEVERITY_DESCRIPTIONS: dict[Severity, str] = {
    Severity.HIGH: (
        "This capability grants direct access to sensitive resources and cannot be fully sandboxed."
    ),
    Severity.MEDIUM: "This capability could leak information or mutate state in unexpected ways.",
    Severity.LOW: "Low-risk read-only access; generally safe but worth noting.",
}


def scan_description(
    manifest: SkillManifest,
    config: PipelineConfig | None = None,
    extra_text: dict[str, str] | None = None,
) -> Stage1Result:
    """Analyse declared capabilities and skill text, returning flags and a score.

    Args:
        manifest: the normalized skill manifest.
        config: pipeline config; defaults are used when omitted.
        extra_text: content outside the manifest fields — markdown bodies, MCP
            env blocks — keyed by a location label. Scanned for injection, since
            that is exactly where a payload hides.

    Score starts at 100; capability risk and injection findings both deduct.
    """
    cfg = config or PipelineConfig()
    flags: list[RiskFlag] = []
    reasons: list[str] = []

    for tool in manifest.tools:
        for cap in tool.capabilities:
            severity = _CAPABILITY_SEVERITY.get(cap, Severity.LOW)
            desc = f"Tool '{tool.name}' declares {cap.value}: {_SEVERITY_DESCRIPTIONS[severity]}"
            flags.append(RiskFlag(capability=cap, severity=severity, description=desc))

    # Deduplicate flags by capability (keep highest severity).
    seen: dict[Capability, RiskFlag] = {}
    for flag in flags:
        existing = seen.get(flag.capability)
        if existing is None or _severity_rank(flag.severity) > _severity_rank(existing.severity):
            seen[flag.capability] = flag
    deduped = list(seen.values())

    deduction = 0
    for flag in deduped:
        if flag.severity == Severity.HIGH:
            deduction += cfg.high_risk_deduction
            reasons.append(f"HIGH: {flag.description}")
        elif flag.severity == Severity.MEDIUM:
            deduction += cfg.medium_risk_deduction
            reasons.append(f"MEDIUM: {flag.description}")
        else:
            deduction += cfg.low_risk_deduction
            reasons.append(f"LOW: {flag.description}")

    injection = _scan_for_injection(manifest, extra_text)
    injection_flags = [
        InjectionFlag(
            category=finding.category.value,
            severity=Severity(finding.severity.value),
            rule=finding.rule,
            description=finding.description,
            location=finding.location,
            evidence=finding.evidence,
        )
        for finding in injection.findings
    ]
    for finding in injection.findings:
        reasons.append(
            f"{finding.severity.value} INJECTION [{finding.rule}] at "
            f"{finding.location}: {finding.description} — {finding.evidence}"
        )
    deduction += injection.score_penalty

    score = max(0, 100 - deduction)
    reasoning = (
        "\n".join(reasons) if reasons else "No risk flags found. Skill appears safe by description."
    )

    return Stage1Result(
        risk_flags=deduped,
        injection_flags=injection_flags,
        initial_score=score,
        reasoning=reasoning,
    )


def _scan_for_injection(
    manifest: SkillManifest,
    extra_text: dict[str, str] | None,
) -> InjectionScanResult:
    result = scan_manifest(manifest)
    for location, text in (extra_text or {}).items():
        result.findings.extend(scan_text(text, location))
    # scan_manifest already deduped its own findings; redo it across the union.
    result.findings = dedupe_findings(result.findings)
    return result


def _severity_rank(sev: Severity) -> int:
    return {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}[sev]
