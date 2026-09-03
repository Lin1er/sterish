"""Stage 3: Final verdict synthesis and trust score calculation."""

import hashlib

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import (
    AuditReport,
    FinalVerdict,
    Severity,
    Stage1Result,
    Stage2Result,
)


def synthesize_verdict(
    report: AuditReport,
    stage1: Stage1Result,
    stage2: Stage2Result,
    config: PipelineConfig | None = None,
) -> AuditReport:
    """Combine stage 1 and stage 2 results into a final verdict and trust score."""
    cfg = config or PipelineConfig()

    # Weighted trust score.
    raw_score = (
        stage1.initial_score * cfg.stage1_weight + _sandbox_score(stage2) * cfg.stage2_weight
    ) // 100
    trust_score = max(0, min(100, raw_score))

    # Determine verdict based on thresholds.
    if stage2.escaped_sandbox:
        verdict = FinalVerdict.DANGEROUS
        trust_score = 0
    elif trust_score >= cfg.safe_threshold:
        verdict = FinalVerdict.SAFE
    elif trust_score >= cfg.warning_threshold:
        verdict = FinalVerdict.WARNING
    else:
        verdict = FinalVerdict.DANGEROUS

    # Build recommendation text.
    recommendation = _build_recommendation(verdict, stage1, stage2, trust_score)

    # Generate evidence hash from the audit data.
    evidence = (
        f"{report.skill_id}|{verdict.value}|{trust_score}"
        f"|{stage1.initial_score}|{_sandbox_score(stage2)}"
    )
    evidence_hash = hashlib.sha256(evidence.encode()).hexdigest()

    report.stage1 = stage1
    report.stage2 = stage2
    report.final_verdict = verdict
    report.trust_score = trust_score
    report.evidence_hash = evidence_hash
    report.recommendation = recommendation
    return report


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
    """Generate a human-readable recommendation."""
    if verdict == FinalVerdict.SAFE:
        return (
            f"Skill passed audit with trust score {trust_score}/100. "
            f"No critical risk flags detected. Safe to use."
        )
    if verdict == FinalVerdict.WARNING:
        return (
            f"Skill has trust score {trust_score}/100. "
            f"Some risk flags: {len(stage1.risk_flags)} description risks, "
            f"{len(stage2.behavioral_flags)} behavioral flags. "
            f"Review before using in production."
        )
    return (
        f"SKILL REJECTED: trust score {trust_score}/100. "
        f"Critical risks found. {len(stage1.risk_flags)} description risks, "
        f"{len(stage2.behavioral_flags)} behavioral flags, "
        f"sandbox escaped: {stage2.escaped_sandbox}. Do not use."
    )
