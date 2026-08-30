from enum import StrEnum

from pydantic import BaseModel, Field


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


class SkillManifest(BaseModel):
    skill_id: str
    name: str
    description: str
    version: str
    permissions: list[str] = Field(default_factory=list)
    tools: list[ToolDef] = Field(default_factory=list)


class Severity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RiskFlag(BaseModel):
    capability: Capability
    severity: Severity
    description: str


class Stage1Result(BaseModel):
    risk_flags: list[RiskFlag] = Field(default_factory=list)
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
    behavioral_flags: list[BehavioralFlag] = Field(default_factory=list)
    observed_calls: list[ObservedCall] = Field(default_factory=list)
    escaped_sandbox: bool = False


class FinalVerdict(StrEnum):
    SAFE = "SAFE"
    DANGEROUS = "DANGEROUS"
    WARNING = "WARNING"


class AuditReport(BaseModel):
    skill_id: str
    stage1: Stage1Result = Field(default_factory=Stage1Result)
    stage2: Stage2Result = Field(default_factory=Stage2Result)
    final_verdict: FinalVerdict = FinalVerdict.SAFE
    trust_score: int = Field(ge=0, le=100, default=100)
    evidence_hash: str = ""
    recommendation: str = ""