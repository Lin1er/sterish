"""Stage 1: Tool description and capability scanning."""

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import (
    Capability,
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

    score = max(0, 100 - deduction)
    reasoning = (
        "\n".join(reasons) if reasons else "No risk flags found. Skill appears safe by description."
    )

    return Stage1Result(risk_flags=deduped, initial_score=score, reasoning=reasoning)


def _severity_rank(sev: Severity) -> int:
    return {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}[sev]
