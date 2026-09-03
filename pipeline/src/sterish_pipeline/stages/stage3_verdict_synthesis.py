"""Stage 3: verdict synthesis.

Two layers, in this order and never the other way round:

1. **Deterministic baseline.** Weighted stage1/stage2 score, then the hard rules in
   ``policy.py``. This runs on every audit, with or without a model, and it is what the
   emitted document is built from.
2. **Optional LLM synthesis** (``llm.py``), which may only *tighten* the baseline. A model
   that answers SAFE over a deterministic DANGEROUS changes nothing; a model that answers
   DANGEROUS over a deterministic SAFE wins. Any failure -- no key, timeout, malformed JSON,
   schema rejection -- is fail-soft: the baseline stands and the reason is recorded in the
   internal report (never in the verdict document, whose schema forbids extra properties).
"""

from __future__ import annotations

import hashlib
import json
import logging

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import (
    AuditReport,
    Capability,
    Finding,
    FinalVerdict,
    Severity,
    SkillManifest,
    Stage1Result,
    Stage2Result,
    Verdict,
    VerdictDocument,
)
from sterish_pipeline.stages import policy

logger = logging.getLogger(__name__)


def synthesize_verdict(
    report: AuditReport,
    stage1: Stage1Result,
    stage2: Stage2Result,
    config: PipelineConfig | None = None,
    llm_inconclusive: bool = False,
) -> AuditReport:
    """Combine stage 1 and stage 2 into a final verdict, trust score and policy decision."""
    cfg = config or PipelineConfig()

    raw_score = (
        stage1.initial_score * cfg.stage1_weight + _sandbox_score(stage2) * cfg.stage2_weight
    ) // 100
    trust_score = max(0, min(100, raw_score))

    decision = policy.decide(stage1, stage2, trust_score, cfg, llm_inconclusive=llm_inconclusive)

    report.stage1 = stage1
    report.stage2 = stage2
    report.final_verdict = decision.verdict
    report.trust_score = decision.score
    report.risk = decision.risk
    report.recommendation_code = decision.recommendation
    report.policy_reasons = decision.reasons
    report.recommendation = _build_recommendation(decision.verdict, stage1, stage2, decision.score)
    report.evidence_hash = compute_evidence_hash(report)
    return report


def compute_evidence_hash(report: AuditReport) -> str:
    """sha256 over the **entire** internal report, not over a five-number summary.

    The scaffold hashed ``f"{skill_id}|{verdict}|{score}|{s1}|{s2}"``, which anchors five
    numbers and leaves every finding unprotected -- the findings being the part a reader
    actually needs to trust (``verdict-json.md`` gap P8). Here the whole report is serialized
    canonically (sorted keys, no whitespace) with ``evidence_hash`` blanked, so the value is
    reproducible by anyone holding the served report.
    """
    payload = report.model_dump(mode="json")
    payload["evidence_hash"] = ""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sandbox_score(stage2: Stage2Result) -> int:
    """Derive a 0-100 score from stage 2 results."""
    if stage2.escaped_sandbox:
        return 0
    score = 100
    for flag in stage2.behavioral_flags:
        if flag.severity == Severity.HIGH:
            score -= 25
        elif flag.severity == Severity.MEDIUM:
            score -= 10
        else:
            score -= 3
    return max(0, score)


def _build_recommendation(
    verdict: FinalVerdict,
    stage1: Stage1Result,
    stage2: Stage2Result,
    trust_score: int,
) -> str:
    """Generate a human-readable recommendation (off-chain report only).

    The verdict document carries the ``ALLOW``/``REVIEW``/``BLOCK`` enum instead; this prose
    is what a dashboard shows underneath it.
    """
    injections = len(stage1.injection_findings)
    if verdict == FinalVerdict.SAFE:
        return (
            f"Skill passed audit with trust score {trust_score}/100. "
            f"No critical risk flags detected. Safe to use."
        )
    if verdict == FinalVerdict.WARNING:
        return (
            f"Skill has trust score {trust_score}/100. "
            f"Some risk flags: {len(stage1.risk_flags)} description risks, "
            f"{injections} text-injection findings, "
            f"{len(stage2.behavioral_flags)} behavioral flags. "
            f"Review before using in production."
        )
    return (
        f"SKILL REJECTED: trust score {trust_score}/100. "
        f"Critical risks found. {len(stage1.risk_flags)} description risks, "
        f"{injections} text-injection findings, "
        f"{len(stage2.behavioral_flags)} behavioral flags, "
        f"sandbox escaped: {stage2.escaped_sandbox}. Do not use."
    )


# --------------------------------------------------------------------------------------
# Verdict document assembly
# --------------------------------------------------------------------------------------


def observed_capabilities(report: AuditReport, manifest: SkillManifest) -> list[Capability]:
    """Declared capabilities plus the ones the prose implies but never declared.

    ``verdict.schema.json`` calls this field "capabilities the skill declares **or was
    observed to exercise**", so a hidden ``read ~/.ssh/id_rsa`` belongs here even though the
    manifest says ``FILE_READ`` only. Otherwise the document would repeat the manifest's own
    lie back to the reader.
    """
    caps: set[Capability] = set(manifest.declared_capabilities())
    for finding in report.stage1.injection_findings:
        if finding.capability is not None:
            caps.add(finding.capability)
    return sorted(caps, key=lambda c: c.value)


def _declared_evidence(manifest: SkillManifest, capability: Capability) -> str:
    for i, tool in enumerate(manifest.tools):
        if capability in tool.capabilities:
            return f"tools[{i}].capabilities"
    return "manifest.tools[*].capabilities"


def build_findings(report: AuditReport, manifest: SkillManifest) -> list[Finding]:
    """Flatten every stage into the schema's ``findings[]`` shape.

    Injection findings keep their ``pattern_id`` in the description text on purpose: the
    document is what a reviewer reads, and "hidden_block" is the fastest way to tell them
    which rule fired.
    """
    findings: list[Finding] = []

    for flag in report.stage1.risk_flags:
        findings.append(
            Finding(
                stage=1,
                capability=flag.capability,
                severity=flag.severity,
                description=flag.description,
                evidence=_declared_evidence(manifest, flag.capability),
            )
        )

    for injection in report.stage1.injection_findings:
        findings.append(
            Finding(
                stage=1,
                capability=injection.capability,
                severity=injection.severity,
                description=f"[{injection.pattern_id}] {injection.description}",
                evidence=injection.evidence,
            )
        )

    for flag in report.stage2.behavioral_flags:
        findings.append(
            Finding(
                stage=2,
                severity=flag.severity,
                description=flag.description,
                evidence=f"stage2: declared-vs-actual on {flag.syscall}",
            )
        )

    if report.policy_reasons:
        findings.append(
            Finding(
                stage=3,
                severity=(
                    Severity.HIGH
                    if report.final_verdict is FinalVerdict.DANGEROUS
                    else Severity.MEDIUM
                    if report.final_verdict is FinalVerdict.WARNING
                    else Severity.LOW
                ),
                description=(
                    f"Synthesis: {report.final_verdict.value} at score {report.trust_score}/100. "
                    + " ".join(report.policy_reasons[:2])
                ),
                evidence="policy.decide over stage1+stage2 findings",
            )
        )

    return findings


def build_verdict_document(
    report: AuditReport,
    manifest: SkillManifest,
    content_hash: str,
    config: PipelineConfig | None = None,
) -> VerdictDocument:
    """Assemble the FROZEN v1 verdict document from a finished report.

    ``content_hash`` must come from ``specs.hash_dir`` (the frozen reference implementation);
    this function will not compute one, because a second implementation of skill identity is
    exactly what ``docs/specs/content-hash.md`` exists to prevent.
    """
    _ = config  # thresholds are already baked into report.risk / report.recommendation_code
    report.content_hash = content_hash
    report.version = manifest.version
    report.capabilities = observed_capabilities(report, manifest)
    report.findings = build_findings(report, manifest)
    report.evidence_hash = compute_evidence_hash(report)

    return VerdictDocument(
        skill_id=manifest.skill_id,
        version=manifest.version,
        content_hash=content_hash,
        verdict=Verdict(report.final_verdict.value),
        risk=report.risk,
        score=report.trust_score,
        capabilities=report.capabilities,
        findings=report.findings,
        recommendation=report.recommendation_code,
        evidence_hash=report.evidence_hash,
    )
