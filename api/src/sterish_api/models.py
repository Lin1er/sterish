from datetime import datetime

from pydantic import BaseModel, Field


class CheckResponse(BaseModel):
    skill_id: str
    verdict: str
    trust_score: int = Field(ge=0, le=100)
    evidence_hash: str
    audit_timestamp: int
    auditor: str


class SkillResponse(BaseModel):
    skill_id: str
    version: str
    verdict: str
    trust_score: int = Field(ge=0, le=100)
    registered_at: int


class SkillListResponse(BaseModel):
    skills: list[SkillResponse]
    total: int
    start: int
    limit: int


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""