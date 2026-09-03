"""Response schemas for the Sterish verification API.

Field names here are the public API contract — `docs/api-spec.md` documents the
same shapes and the two must be kept in step.
"""

from pydantic import BaseModel, Field


class SkillVersionResponse(BaseModel):
    """One registered version of a skill."""

    version: str
    content_hash: str
    registered_at: int


class CheckResponse(BaseModel):
    """Answer to "is this skill safe?" for a single skill."""

    skill_id: str
    verdict: str
    trust_score: int = Field(ge=0, le=100)
    evidence_hash: str = ""
    evidence: str = ""
    audit_timestamp: int = 0
    auditor: str = ""
    versions: list[SkillVersionResponse] = Field(default_factory=list)


class SkillListItem(BaseModel):
    """One row of the registry listing."""

    skill_id: str
    verdict: str
    trust_score: int = Field(ge=0, le=100)
    versions: int = 0
    audit_timestamp: int = 0


class SkillListResponse(BaseModel):
    skills: list[SkillListItem]
    total: int
    start: int
    limit: int


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    registry_contract_id: str = ""
    network: str = ""


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""
