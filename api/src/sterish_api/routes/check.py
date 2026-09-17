"""Verification endpoints, per docs/api-spec.md v1.0.0.

Design rule 1 from the spec: the unit of truth is (skill_id, version), or better,
content_hash. No endpoint here returns a verdict keyed on skill_id alone.
"""

import re

from fastapi import APIRouter, Query, Request

from .. import chain, fanout, indexer, registry_snapshot, skills
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
from . import reports

router = APIRouter()

# Handlers here are sync `def`, not `async def`, on purpose. Every call they make
# — the Soroban simulations, the facilitator round trips, the licence mint — is
# blocking IO. Declared async they would run ON the event loop and stall every
# other request for their duration; a mint polls the ledger for several seconds,
# so one purchase made the whole API unresponsive. FastAPI runs sync handlers in
# a threadpool, which is exactly what this work wants.

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

# api-spec section 6: one get_version per version is one RPC round trip, so cap the
# fan-out rather than letting a skill with many versions stall the request.
MAX_VERSION_FANOUT = 50


def _version_record_or_none(skill_id: str, version: str) -> dict | None:
    """One row's chain read, with the per-row failure policy applied.

    Returned rather than raised so a version that is listed but unreadable is skipped
    instead of failing the whole page. This runs on a fan-out worker thread, so it must
    not touch the indexer's SQLite connection — evidence is built by the caller.
    """
    try:
        return chain.get_version(skill_id, version)
    except chain.ContractError:
        return None


def _report_uri(skill_id: str, version: str) -> str | None:
    """Link to the report at api-spec 3.6, or null when there is nothing to link to.

    Two conditions, not one. A base URL says where reports are served from; the file
    on disk says whether this particular version has one. Advertising on config alone
    handed clients a link that 404s for every version audited before reports existed,
    which is the failure the old `PLANNED` gate was avoiding by never advertising at all.

    The path is `/reports/{skill_id}/{version}` — no `.json` suffix. It used to carry
    one, which meant the URI this API advertised and the URI the pipeline generated for
    the same report were two different strings, and neither was the route that now
    serves it.
    """
    if not settings.report_base_url:
        return None
    if reports.report_path(skill_id, version) is None:
        return None
    return f"{settings.report_base_url}/reports/{skill_id}/{version}"


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
def check_by_hash(content_hash: str):
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
def check_by_name(skill_id: str, version: str):
    """Same body as check-by-hash, resolved by name. Use it for display; prefer
    by-hash for a security decision, because asking by name trusts the name."""
    if not skill_id or not version:
        raise ApiError(400, "INVALID_PARAMETER", "skill_id and version must be non-empty")
    return _check_response(chain.get_version(skill_id, version))


@router.get("/skills/{skill_id}", response_model=SkillDetailResponse)
def skill_detail(skill_id: str):
    if not skill_id:
        raise ApiError(400, "INVALID_PARAMETER", "skill_id must be non-empty")

    entry = chain.query_skill(skill_id)

    # One RPC per version, overlapped (STE-33). `_evidence` stays out here on the
    # request thread: it reads the indexer's SQLite handle, which the workers must not.
    records = fanout.map_bounded(
        lambda version: _version_record_or_none(skill_id, version),
        entry["versions"][:MAX_VERSION_FANOUT],
        settings.chain_concurrency,
    )

    audited: list[AuditedVersion] = []
    for record in records:
        if record is None or record["verdict"] == "UNAUDITED":
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


VERDICTS = ("SAFE", "WARNING", "DANGEROUS", "UNAUDITED")
SORTS = ("registered_at", "trust_score", "skill_id")
ORDERS = ("asc", "desc")
MAX_QUERY_LENGTH = 200

# Parameters the ticket considered and rejected. Answered with a pointer to what to
# use instead, rather than silently ignored and returning an unfiltered page.
REJECTED_PARAMETERS = {
    "verified": "is_verified is true exactly when the verdict is SAFE; use verdict=SAFE",
    "owner": "the registry has one owner today; filtering by owner is not supported",
}


def _invalid(detail: str) -> ApiError:
    return ApiError(400, "INVALID_PARAMETER", detail)


@router.get("/skills", response_model=SkillListResponse)
def list_skills(
    request: Request,
    start: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_test: bool = Query(
        default=False,
        description="Include skills registered under a test namespace. Hidden by "
        "default; `hidden_test_entries` says how many, and `chain_total` is always "
        "the real on-chain count.",
    ),
    verdict: str | None = Query(default=None),
    q: str | None = Query(default=None),
    stale_audit: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
):
    for name, why in REJECTED_PARAMETERS.items():
        if name in request.query_params:
            raise _invalid(f"{name} is not a supported parameter: {why}")

    if all(p is None for p in (verdict, q, stale_audit, sort, order)):
        return _list_plain(start, limit, include_test)
    return _list_filtered(start, limit, include_test, verdict, q, stale_audit, sort, order)


def _list_filtered(
    start: int,
    limit: int,
    include_test: bool,
    verdict: str | None,
    q: str | None,
    stale_audit: str | None,
    sort: str | None,
    order: str | None,
) -> SkillListResponse:
    """Filter and sort the whole registry, then page (STE-34, api-spec 3.4).

    Rows are chosen from a chain-read snapshot (registry_snapshot.py) and then the
    returned page is re-read live. A row whose live verdict no longer matches the
    `verdict` filter is left out and counted in `excluded_stale`, and the snapshot is
    dropped so the next request agrees with the chain again.

    Test namespaces are hidden exactly as in the plain listing (STE-18), and the three
    counts stay honest: `total` is what the filters leave, `chain_total` the contract's
    own count, and `hidden_test_entries` the test-namespace rows that matched every
    other filter and were hidden only because of their namespace.
    """
    if verdict is not None and verdict not in VERDICTS:
        raise _invalid(f"verdict must be one of {', '.join(VERDICTS)}")
    if q is not None and not q.strip():
        raise _invalid("q must not be empty")
    if q is not None and len(q) > MAX_QUERY_LENGTH:
        raise _invalid(f"q must be at most {MAX_QUERY_LENGTH} characters")
    if stale_audit is not None and stale_audit not in ("true", "false"):
        raise _invalid("stale_audit must be true or false")
    if sort is not None and sort not in SORTS:
        raise _invalid(f"sort must be one of {', '.join(SORTS)}")
    if order is not None and order not in ORDERS:
        raise _invalid("order must be asc or desc")

    snapshot = registry_snapshot.get()
    needle = q.strip().lower() if q is not None else None
    want_stale = None if stale_audit is None else stale_audit == "true"

    def matches(row: registry_snapshot.Row) -> bool:
        if needle is not None and needle not in row.skill_id.lower():
            return False
        if want_stale is not None and row.stale_audit is not want_stale:
            return False
        if verdict is not None:
            if row.read_failed:
                return False  # unknown is not UNAUDITED, and not anything else either
            if (row.verdict or "UNAUDITED") != verdict:
                return False
        return True

    matched = [row for row in snapshot.rows if matches(row)]
    hidden = 0 if include_test else sum(1 for row in matched if row.is_test)
    rows = matched if include_test else [row for row in matched if not row.is_test]
    rows = _sorted(rows, sort or "registered_at", order or "desc")

    total = len(rows)
    page = rows[start : start + limit]

    def live(row: registry_snapshot.Row) -> dict | None:
        if not row.latest_audited_version:
            return None
        return _version_record_or_none(row.skill_id, row.latest_audited_version)

    records = fanout.map_bounded(live, page, settings.chain_concurrency)

    items: list[SkillListItem] = []
    excluded = 0
    for row, record in zip(page, records, strict=True):
        if verdict is not None:
            live_verdict = record["verdict"] if record else None
            unreadable = record is None and row.latest_audited_version is not None
            if unreadable or (live_verdict or "UNAUDITED") != verdict:
                excluded += 1
                continue
        items.append(_list_item(row.as_entry(), record))

    if excluded:
        registry_snapshot.invalidate()

    return SkillListResponse(
        skills=items,
        total=total,
        start=start,
        limit=limit,
        chain_total=snapshot.chain_total,
        hidden_test_entries=hidden,
        include_test=include_test,
        as_of=int(snapshot.built_at),
        excluded_stale=excluded,
    )


def _sorted(
    rows: list[registry_snapshot.Row], sort: str, order: str
) -> list[registry_snapshot.Row]:
    """Stable, deterministic ordering. Ties break on skill_id ascending.

    Rows with no trust score (never audited, or unreadable) sort LAST in both
    directions: "lowest trust first" must not open with rows that have no trust score.
    """
    descending = order == "desc"
    by_id = sorted(rows, key=lambda r: r.skill_id)
    if sort == "skill_id":
        return list(reversed(by_id)) if descending else by_id
    if sort == "registered_at":
        return sorted(by_id, key=lambda r: r.registered_at, reverse=descending)

    scored = [r for r in by_id if r.trust_score is not None]
    unscored = [r for r in by_id if r.trust_score is None]
    return sorted(scored, key=lambda r: r.trust_score, reverse=descending) + unscored


def _list_item(entry: dict, record: dict | None) -> SkillListItem:
    verdict = score = verified = None
    if record is not None:
        verdict = record["verdict"]
        score = record["trust_score"]
        verified = record["is_verified"]
    return SkillListItem(
        skill_id=entry["skill_id"],
        owner=entry["owner"],
        registered_at=entry["registered_at"],
        version_count=len(entry["versions"]),
        latest_version=entry["latest_version"],
        latest_audited_version=entry["latest_audited_version"],
        latest_audited_verdict=verdict,
        latest_audited_trust_score=score,
        latest_audited_is_verified=verified,
    )


def _list_plain(start: int, limit: int, include_test: bool) -> SkillListResponse:
    """The listing without STE-34 parameters: registration order, test namespaces
    hidden unless asked for (STE-18). Unchanged by STE-34."""
    entries, total, chain_total, hidden = skills.visible_page(start, limit, include_test)

    def _latest_audited_record(entry: dict) -> dict | None:
        latest_audited = entry["latest_audited_version"]
        if not latest_audited:
            return None
        return _version_record_or_none(entry["skill_id"], latest_audited)

    # The row reads are independent, so overlap them instead of paying one RPC round
    # trip per row in series (STE-33). Order is preserved, so this zips back cleanly.
    records = fanout.map_bounded(_latest_audited_record, entries, settings.chain_concurrency)

    items = [_list_item(entry, record) for entry, record in zip(entries, records, strict=True)]

    return SkillListResponse(
        skills=items,
        total=total,
        start=start,
        limit=limit,
        chain_total=chain_total,
        hidden_test_entries=hidden,
        include_test=include_test,
    )


@router.get("/feed", response_model=FeedResponse)
def activity_feed(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_test: bool = Query(
        default=False,
        description="Include events from test namespaces. Hidden by default, with "
        "`hidden_test_events` reporting how many were left out.",
    ),
):
    """Indexed registry activity, newest first. Served from the cache by definition —
    it is a convenience feed, not a verdict source.

    Test namespaces are hidden here for the same reason as in `/skills`: 47 of the 66
    registered skills are scaffolding no contract call can remove, and a feed they
    dominate shows activity nobody performed on purpose."""
    rows, total, hidden = indexer.feed(limit=limit, offset=offset, include_test=include_test)
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
        hidden_test_events=hidden,
        include_test=include_test,
    )
