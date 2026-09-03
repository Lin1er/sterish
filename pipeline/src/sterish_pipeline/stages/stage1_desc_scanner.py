"""Stage 1: declared-capability scanning (1a) merged with text scanning (1b).

``scan_description`` is the original scaffold path and is deliberately left alone: it reads
only the ``capabilities`` a manifest *declares*. ``run_stage1`` is what the pipeline calls --
it runs ``scan_description`` AND ``injection_rules.scan_injection`` over the same manifest and
merges both into one ``Stage1Result``.

Keeping the two callable separately is not tidiness, it is the regression test:
``tests/test_gap_closed.py`` calls ``scan_description`` alone on the poisoned-pdf fixture and
asserts it scores 97/SAFE, which is the gap this ticket closes.
"""

from pathlib import Path

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import (
    Capability,
    RiskFlag,
    Severity,
    SkillManifest,
    Stage1Result,
)
from sterish_pipeline.stages import policy
from sterish_pipeline.stages.injection_rules import scan_injection

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
        "This capability grants direct access to sensitive resources and cannot be "
        "fully sandboxed."
    ),
    Severity.MEDIUM: "This capability could leak information or mutate state in unexpected ways.",
    Severity.LOW: "Low-risk read-only access; generally safe but worth noting.",
}


def scan_description(
    manifest: SkillManifest,
    config: PipelineConfig | None = None,
) -> Stage1Result:
    """Analyse declared tools and permissions, returning risk flags and a score.

    Score starts at 100 and deducts points for each risk flag found.
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
        existing_rank = -1 if existing is None else _severity_rank(existing.severity)
        if _severity_rank(flag.severity) > existing_rank:
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

    score = max(0, 100 - deduction)
    reasoning = (
        "\n".join(reasons)
        if reasons
        else "No risk flags found. Skill appears safe by description."
    )

    return Stage1Result(risk_flags=deduped, initial_score=score, reasoning=reasoning)


def _severity_rank(sev: Severity) -> int:
    return {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}[sev]


def run_stage1(
    manifest: SkillManifest,
    config: PipelineConfig | None = None,
    skill_dir: Path | str | None = None,
) -> Stage1Result:
    """Full stage 1: declared capabilities (1a) + description injection scan (1b).

    The score starts from the declared-capability score and is reduced further by the
    injection findings, at a heavier rate (see ``PipelineConfig.injection_*_deduction``).
    A critical-class pattern zeroes it outright -- the policy caps the final score anyway,
    but a stage score of 0 keeps the two layers telling the same story.
    """
    cfg = config or PipelineConfig()
    declared = scan_description(manifest, cfg)
    scan = scan_injection(manifest, skill_dir)

    deduction = policy.injection_deduction(scan.findings, cfg)
    criticals = policy.critical_findings(scan.findings)
    score = 0 if criticals else max(0, declared.initial_score - deduction)

    reasons = [declared.reasoning] if declared.reasoning else []
    if scan.findings:
        reasons.append(
            f"Scanned {scan.text_scanned} text field(s); "
            f"{len(scan.findings)} injection finding(s) across "
            f"{len(sorted({f.pattern_id for f in scan.findings}))} pattern(s)."
        )
        for finding in scan.findings:
            reasons.append(
                f"{finding.severity.value} [{finding.pattern_id}] {finding.description} "
                f"({finding.evidence})"
            )
    if criticals:
        ids = ", ".join(sorted({f.pattern_id for f in criticals}))
        reasons.append(f"CRITICAL pattern class present ({ids}); stage 1 score forced to 0.")
    else:
        reasons.append(f"Scanned {scan.text_scanned} text field(s); no injection findings.")

    return Stage1Result(
        risk_flags=declared.risk_flags,
        injection_findings=scan.findings,
        text_scanned=scan.text_scanned,
        initial_score=score,
        reasoning="\n".join(reasons),
    )
