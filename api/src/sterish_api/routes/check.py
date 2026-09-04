"""Verification endpoints, per docs/api-spec.md v1.0.0.

Design rule 1 from the spec: the unit of truth is (skill_id, version), or better,
content_hash. No endpoint here returns a verdict keyed on skill_id alone.
"""

import re

from fastapi import APIRouter, Query

from .. import chain, indexer
from ..config import settings
from ..errors import ApiError
from ..models import (
    AuditedVersion,
    Evidence,
    FeedItem,
    FeedResponse,
    SkillDetailResponse,
    SkillListItem,
    SkillListResponse,
    VersionCheckResponse,
    iso_or_none,
)

router = APIRouter()

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

# api-spec section 6: one get_version per version is one RPC round trip, so cap the
# fan-out rather than letting a skill with many versions stall the request.
MAX_VERSION_FANOUT = 50


def _report_uri(skill_id: str, version: str) -> str | None:
    """PLANNED endpoint (api-spec 3.6). Advertised only once a base URL is configured,
    so we never hand a client a link that 404s."""
    if not settings.report_base_url:
        return None
    return f"{settings.report_base_url}/reports/{skill_id}/{version}.json"


def _evidence(record: dict) -> Evidence:
    skill_id, version = record["skill_id"], record["version"]
    reg_tx = indexer.tx_for(skill_id, version, "version_registered")
    # A re-audit emits verdict_flipped; that transaction is the newer evidence.
    audit_tx = indexer.tx_for(skill_id, version, "verdict_flipped") or indexer.tx_for(
        skill_id, version, "version_recorded"
    )
    if record["verdict"] == "UNAUDITED":
        audit_tx = None

    return Evidence(
        registry_contract_id=settings.registry_contract_id,
        contract_url=settings.contract_url(settings.registry_contract_id),
        registration_tx=reg_tx,
        registration_tx_url=settings.tx_url(reg_tx) if reg_tx else None,
        audit_tx=audit_tx,
        audit_tx_url=settings.tx_url(audit_tx) if audit_tx else None,
        evidence_hash=record["evidence_hash"],
        report_uri=_report_uri(skill_id, version),
    )


def _check_response(record: dict) -> VersionCheckResponse:
    return VersionCheckResponse(
        **{k: record[k] for k in (
            "skill_id", "version", "content_hash", "verdict", "trust_score",
            "is_verified", "owner", "auditor", "registered_at", "audited_at",
        )},
        audited_at_iso=iso_or_none(record["audited_at"]),
        evidence=_evidence(record),
    )


@router.get("/check/by-hash/{content_hash}", response_model=VersionCheckResponse)
async def check_by_hash(content_hash: str):
    """The primary path: 'are *these bytes* audited?'.

    A single changed byte produces a different hash, which misses — that is what stops
    a poisoned v2 from inheriting v1's badge.
    """
    if not _HASH_RE.match(content_hash):
        # Uppercase is rejected rather than normalised: a client that produced it has a
        # bug worth surfacing (api-spec 3.1).
        raise ApiError(
            400,
            "INVALID_CONTENT_HASH",
            "content_hash must be exactly 64 lowercase hex characters",
        )

    record = chain.lookup_by_hash(content_hash)
    if record is None:
        # `is_verified: false` rides along in the 404 body so a client reading only that
        # field cannot mistake "unknown" for anything but unverified.
        raise ApiError(
            404,
            "NOT_FOUND",
            f"content_hash {content_hash} is not registered",
            {"content_hash": content_hash, "is_verified": False},
        )
    return _check_response(record)


@router.get("/check/{skill_id}/{version}", response_model=VersionCheckResponse)
async def check_by_name(skill_id: str, version: str):
    """Same body as check-by-hash, resolved by name. Use it for display; prefer
    by-hash for a security decision, because asking by name trusts the name."""
    if not skill_id or not version:
        raise ApiError(400, "INVALID_PARAMETER", "skill_id and version must be non-empty")
    return _check_response(chain.get_version(skill_id, version))


@router.get("/skills/{skill_id}", response_model=SkillDetailResponse)
async def skill_detail(skill_id: str):
    if not skill_id:
        raise ApiError(400, "INVALID_PARAMETER", "skill_id must be non-empty")

    entry = chain.query_skill(skill_id)
    audited: list[AuditedVersion] = []

    for version in entry["versions"][:MAX_VERSION_FANOUT]:
        try:
            record = chain.get_version(skill_id, version)
        except chain.ContractError:
            continue  # listed but unreadable; skip rather than fail the whole response
        if record["verdict"] == "UNAUDITED":
            continue
        audited.append(
            AuditedVersion(
                version=record["version"],
                content_hash=record["content_hash"],
                verdict=record["verdict"],
                trust_score=record["trust_score"],
                is_verified=record["is_verified"],
                audited_at=record["audited_at"],
                evidence=_evidence(record),
            )
        )

    latest_audited = entry["latest_audited_version"]
    warning = None
    if latest_audited and entry["latest_version"] != latest_audited:
        # Name the confusion out loud rather than letting a UI infer a badge.
        warning = (
            f"latest_version {entry['latest_version']} is NOT the audited version. "
            "A verdict applies to one version only."
        )

    return SkillDetailResponse(
        skill_id=entry["skill_id"],
        owner=entry["owner"],
        registered_at=entry["registered_at"],
        versions=entry["versions"],
        latest_version=entry["latest_version"],
        latest_audited_version=latest_audited,
        audited_versions=audited,
        warning=warning,
    )


@router.get("/skills", response_model=SkillListResponse)
async def list_skills(
    start: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    entries = chain.query_all_skills(start, limit)
    items: list[SkillListItem] = []

    for entry in entries:
        latest_audited = entry["latest_audited_version"]
        verdict = score = verified = None
        if latest_audited:
            try:
                record = chain.get_version(entry["skill_id"], latest_audited)
                verdict = record["verdict"]
                score = record["trust_score"]
                verified = record["is_verified"]
            except chain.ContractError:
                pass
        items.append(
            SkillListItem(
                skill_id=entry["skill_id"],
                owner=entry["owner"],
                registered_at=entry["registered_at"],
                version_count=len(entry["versions"]),
                latest_version=entry["latest_version"],
                latest_audited_version=latest_audited,
                latest_audited_verdict=verdict,
                latest_audited_trust_score=score,
                latest_audited_is_verified=verified,
            )
        )

    return SkillListResponse(
        skills=items, total=chain.get_skill_count(), start=start, limit=limit
    )


@router.get("/feed", response_model=FeedResponse)
async def activity_feed(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Indexed registry activity, newest first. Served from the cache by definition —
    it is a convenience feed, not a verdict source."""
    rows, total = indexer.feed(limit=limit, offset=offset)
    return FeedResponse(
        events=[
            FeedItem(
                event=r["event"],
                skill_id=r["skill_id"],
                version=r["version"] or None,
                content_hash=r["content_hash"],
                verdict=r["verdict"],
                trust_score=r["trust_score"],
                ledger=r["ledger"],
                tx_hash=r["tx_hash"],
                tx_url=settings.tx_url(r["tx_hash"]),
                occurred_at=r["occurred_at"],
                occurred_at_iso=iso_or_none(r["occurred_at"]),
            )
            for r in rows
        ],
        total=total,
        indexer_enabled=settings.indexer_enabled,
        last_indexed_ledger=indexer.last_indexed_ledger(),
    )
