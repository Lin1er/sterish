"""Pipeline data model.

Two families live here:

* the *internal* audit model (``SkillManifest``, ``Stage1Result``, ``Stage2Result``,
  ``AuditReport``) — free to grow, it never leaves the process; and
* the *emitted* model (``VerdictDocument``, ``Finding``) — a 1:1 mirror of the FROZEN
  ``docs/specs/verdict.schema.json``. Every field, enum member, pattern and bound below is
  copied from that schema on purpose: pydantic rejects a bad document at construction time,
  the schema rejects it again at the boundary, and the tests assert both agree.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Capability(StrEnum):
    FILE_READ = "FILE_READ"
    FILE_WRITE = "FILE_WRITE"
    NETWORK_OUTBOUND = "NETWORK_OUTBOUND"
    WALLET_ACCESS = "WALLET_ACCESS"
    ENV_READ = "ENV_READ"
    SECRET_READ = "SECRET_READ"


class ToolDef(BaseModel):
    name: str
    description: str
    input_schema: dict = Field(default_factory=dict)
    capabilities: list[Capability] = Field(default_factory=list)
    #: True when the normaliser synthesised this tool rather than the author declaring it.
    #: See `SkillManifest.declared_capabilities(explicit_only=True)`.
    implied: bool = False


class Entrypoint(BaseModel):
    """How a skill starts a process — when it starts one at all (STE-40).

    Only MCP servers have one. An Agent Skill published as markdown executes nothing:
    its risk is what it *instructs the agent* to do, which is stage 1's territory. The
    field is therefore optional, and `None` means "nothing to run", never "ran clean".
    """

    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class SkillManifest(BaseModel):
    skill_id: str
    name: str
    description: str
    version: str
    permissions: list[str] = Field(default_factory=list)
    tools: list[ToolDef] = Field(default_factory=list)
    #: Present only when the source declares an executable server. See `Entrypoint`.
    entrypoint: Entrypoint | None = None

    def declared_capabilities(self, explicit_only: bool = False) -> set[Capability]:
        """Union of every capability declared by any tool.

        `explicit_only` drops tools the normaliser synthesised rather than ones the author
        wrote. Stage 2 needs that distinction: the MCP normaliser adds a `:server` tool
        carrying NETWORK_OUTBOUND and ENV_READ to *any* manifest with a command, on the
        sound stage-1 reasoning that launching a process grants it those regardless. But
        comparing observed behaviour against that set makes "declared" vacuous — every
        executable skill would implicitly have declared the network, and a skill that
        promises "local only" then phones home would come back clean.
        """
        out: set[Capability] = set()
        for tool in self.tools:
            if explicit_only and tool.implied:
                continue
            out.update(tool.capabilities)
        return out


class Severity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
}


class RiskFlag(BaseModel):
    capability: Capability
    severity: Severity
    description: str


class InjectionFinding(BaseModel):
    """One hit from the stage-1 description-injection scanner.

    Unlike ``RiskFlag`` — which reports what a manifest *declares* — this reports what the
    prose *says*, which is the whole point: a skill that declares ``capabilities: []`` and
    hides ``read ~/.ssh/id_rsa`` inside a description is invisible to the declared-capability
    path and is precisely the MCP tool-poisoning class the product claims to catch.
    """

    pattern_id: str
    severity: Severity
    description: str
    field_path: str = Field(description="Where the text lives, e.g. 'tools[0].description'")
    snippet: str = Field(default="", description="The offending excerpt, truncated")
    capability: Capability | None = Field(
        default=None,
        description="Capability the text implies, when the detector can attribute one.",
    )

    @property
    def evidence(self) -> str:
        """Schema-shaped evidence pointer: field location plus the offending excerpt."""
        if not self.snippet:
            return self.field_path
        return f'{self.field_path}: "{self.snippet}"'


class Stage1Result(BaseModel):
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    injection_findings: list[InjectionFinding] = Field(default_factory=list)
    text_scanned: int = Field(default=0, description="Number of text fields fed to the scanner")
    initial_score: int = Field(ge=0, le=100, default=100)
    reasoning: str = ""


class BehavioralFlag(BaseModel):
    syscall: str
    expected: bool
    severity: Severity
    description: str


class ObservedCall(BaseModel):
    syscall: str
    args: dict = Field(default_factory=dict)
    timestamp: float = 0.0


class Stage2Result(BaseModel):
    """What running the skill revealed — or that there was nothing to run.

    `applicable=False` is the important state and the reason this is not just an empty
    result. A skill with no entrypoint produced no observations, and "no observations"
    must never be read as "behaved well". Rewarding the absence of code with a clean
    result is the same category error this project already fixed twice: in the regex
    scanner (STE-36) and in the model's own reasoning (STE-39).
    """

    behavioral_flags: list[BehavioralFlag] = Field(default_factory=list)
    observed_calls: list[ObservedCall] = Field(default_factory=list)
    escaped_sandbox: bool = False
    #: False when nothing was executed: no entrypoint, or no sandbox runtime available.
    applicable: bool = False
    #: Human-readable reason, always set. Ends up in the report so a reader can tell
    #: "clean" from "never ran".
    detail: str = "no entrypoint; nothing to execute"


class FinalVerdict(StrEnum):
    """Verdicts the pipeline can legitimately emit. ``UNAUDITED`` is deliberately absent."""

    SAFE = "SAFE"
    DANGEROUS = "DANGEROUS"
    WARNING = "WARNING"


# ---------------------------------------------------------------------------
# Emitted model — mirrors docs/specs/verdict.schema.json (FROZEN, STE-10)
# ---------------------------------------------------------------------------

SPEC_VERSION = "1.0.0"

_SHA256_HEX = r"^[0-9a-f]{64}$"
_SKILL_ID = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$"
_SEMVER = (
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
_SPEC_VERSION = r"^1\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"


class Verdict(StrEnum):
    """``$defs/Verdict``. Four values; maps 1:1 to ``AuditVerdict`` in contracts/registry."""

    SAFE = "SAFE"
    DANGEROUS = "DANGEROUS"
    WARNING = "WARNING"
    UNAUDITED = "UNAUDITED"


class Risk(StrEnum):
    """``$defs/Risk``. Human-facing band; off-chain only."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Recommendation(StrEnum):
    """``$defs/Recommendation``. Machine-actionable, not prose."""

    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


VERDICT_RANK: dict[Verdict, int] = {
    Verdict.SAFE: 0,
    Verdict.UNAUDITED: 1,
    Verdict.WARNING: 2,
    Verdict.DANGEROUS: 3,
}
RISK_RANK: dict[Risk, int] = {
    Risk.NONE: 0,
    Risk.LOW: 1,
    Risk.MEDIUM: 2,
    Risk.HIGH: 3,
    Risk.CRITICAL: 4,
}
RECOMMENDATION_RANK: dict[Recommendation, int] = {
    Recommendation.ALLOW: 0,
    Recommendation.REVIEW: 1,
    Recommendation.BLOCK: 2,
}


class Finding(BaseModel):
    """``$defs/Finding``. ``capability`` is the only optional member."""

    model_config = ConfigDict(extra="forbid")

    stage: int = Field(ge=1, le=3)
    capability: Capability | None = None
    severity: Severity
    description: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class VerdictDocument(BaseModel):
    """The frozen v1 verdict document. ``additionalProperties: false`` at both levels."""

    model_config = ConfigDict(extra="forbid")

    spec_version: str = Field(default=SPEC_VERSION, pattern=_SPEC_VERSION)
    skill_id: str = Field(min_length=3, max_length=255, pattern=_SKILL_ID)
    version: str = Field(pattern=_SEMVER)
    content_hash: str = Field(pattern=_SHA256_HEX)
    verdict: Verdict
    risk: Risk
    score: int = Field(ge=0, le=100)
    capabilities: list[Capability] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    recommendation: Recommendation
    evidence_hash: str = Field(pattern=_SHA256_HEX)


def to_verdict_json(document: VerdictDocument) -> dict:
    """Serialize a ``VerdictDocument`` into the exact JSON shape the frozen schema accepts.

    ``exclude_none`` matters: ``findings[].capability`` is optional in the schema, and the
    schema sets ``additionalProperties: false``, so emitting ``"capability": null`` for a
    behavioural finding would be rejected (null is not in the Capability enum).
    """
    return document.model_dump(mode="json", exclude_none=True)


class AuditReport(BaseModel):
    """Internal, off-chain audit report.

    Superset of the verdict document: it also carries the reasoning, the LLM audit trail and
    the free-text recommendation, none of which may appear in the emitted document.
    """

    skill_id: str
    version: str = ""
    content_hash: str = ""
    stage1: Stage1Result = Field(default_factory=Stage1Result)
    stage2: Stage2Result = Field(default_factory=Stage2Result)
    final_verdict: FinalVerdict = FinalVerdict.SAFE
    trust_score: int = Field(ge=0, le=100, default=100)
    evidence_hash: str = ""
    recommendation: str = ""
    # --- fields added by STE-14 (policy + LLM audit trail) ---
    risk: Risk = Risk.NONE
    recommendation_code: Recommendation = Recommendation.ALLOW
    capabilities: list[Capability] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    policy_reasons: list[str] = Field(default_factory=list)
    llm_used: bool = False
    llm_attempted: bool = False
    llm_model: str = ""
    llm_notes: list[str] = Field(default_factory=list)
