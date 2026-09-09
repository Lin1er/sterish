"""Response models, shaped exactly as docs/api-spec.md v1.0.0 freezes them.

The scaffold's models predated the STE-10 freeze: they carried a skill-level
`latest_verdict`, which is the inheritance bug STE-5 removed from the contract
(auditing v1 said nothing about v2). Nothing here returns a verdict keyed on
skill_id alone.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


def iso_or_none(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Evidence(BaseModel):
    """api-spec section 2. Transaction fields come from the indexer; they are served as
    null when the indexer has not seen the event yet, never omitted and never faked."""

    registry_contract_id: str
    contract_url: str
    registration_tx: str | None = None
    registration_tx_url: str | None = None
    audit_tx: str | None = None
    audit_tx_url: str | None = None
    evidence_hash: str | None = None
    report_uri: str | None = None


class VersionCheckResponse(BaseModel):
    """Body of GET /check/by-hash/{content_hash} and GET /check/{skill_id}/{version}."""

    skill_id: str
    version: str
    content_hash: str
    verdict: str
    trust_score: int = Field(ge=0, le=100)
    is_verified: bool
    owner: str
    auditor: str | None = None
    registered_at: int
    audited_at: int | None = None
    audited_at_iso: str | None = None
    evidence: Evidence


class AuditedVersion(BaseModel):
    version: str
    content_hash: str
    verdict: str
    trust_score: int = Field(ge=0, le=100)
    is_verified: bool
    audited_at: int | None = None
    evidence: Evidence


class SkillDetailResponse(BaseModel):
    """GET /skills/{skill_id}. Deliberately carries no verdict field at any level."""

    skill_id: str
    owner: str
    registered_at: int
    versions: list[str]
    latest_version: str
    latest_audited_version: str | None = None
    audited_versions: list[AuditedVersion] = []
    warning: str | None = None


class SkillListItem(BaseModel):
    """Verdict fields are prefixed `latest_audited_` on purpose: a bare `verdict` on a
    list row is what let a UI badge a skill whose newest version was never audited."""

    skill_id: str
    owner: str
    registered_at: int
    version_count: int
    latest_version: str
    latest_audited_version: str | None = None
    latest_audited_verdict: str | None = None
    latest_audited_trust_score: int | None = None
    latest_audited_is_verified: bool | None = None


class SkillListResponse(BaseModel):
    skills: list[SkillListItem]
    total: int
    start: int
    limit: int


class FeedItem(BaseModel):
    """One indexed registry event, newest first. Consumed by the dashboard (STE-21)."""

    event: str
    skill_id: str
    version: str | None = None
    content_hash: str | None = None
    verdict: str | None = None
    trust_score: int | None = None
    ledger: int
    tx_hash: str
    tx_url: str
    occurred_at: int | None = None
    occurred_at_iso: str | None = None


class FeedResponse(BaseModel):
    events: list[FeedItem]
    total: int
    indexer_enabled: bool
    last_indexed_ledger: int | None = None


class LicenseStatusResponse(BaseModel):
    """`GET /license/{skill_id}/{version}` (STE-35).

    No verdict, no trust score, no evidence: this answers one question — does this
    agent hold a licence for this exact version — and the tokens contract is the whole
    answer. A caller that also wants the verdict asks `/check`, which is a different
    read against a different contract.
    """

    skill_id: str
    version: str
    agent: str
    held: bool
    tokens_contract_id: str
    contract_url: str


class HealthResponse(BaseModel):
    status: str
    version: str
    network: str
    registry_contract_id: str
    rpc_url: str
    rpc_reachable: bool
    indexer_lag_ledgers: int | None = None
    # The paid path depends on a third party. Reported separately so a caller can
    # tell "Sterish is down" from "you cannot buy a licence right now": reads and
    # existing licence holders are unaffected when this is false.
    facilitator_reachable: bool | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""
