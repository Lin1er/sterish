"""The whole registry, read from chain, for filtering and sorting `GET /skills` (STE-34).

A filter has to run over every row before a page is cut, or it lies: "highest trust
first" that only ranks the twenty rows that happened to be fetched is worse than no
sort at all. So the server needs a view of the whole registry.

That view is built from the **chain**, not from the SQLite index, although the ticket
suggested the index. The index is filled from `getEvents`, which only reaches back
as far as the RPC node retains events; a rebuilt index silently lacks every skill
registered before that window, and `verdict=SAFE` would quietly return fewer rows
than exist. That is the failure `test_cache_is_not_source_of_truth.py` exists to
forbid: delete the cache and the answers must stay correct.

Freshness. The view is at most `STERISH_SKILLS_SNAPSHOT_TTL` seconds old (default 30,
inside the 60 s per-version caching api-spec §6 already allows), and is dropped
early whenever the indexer stores a new registry event. It is only used to **choose**
rows: the rows actually returned are re-read from chain on every request, and a row
whose live verdict no longer matches the filter is left out (see routes/check.py).

Test namespaces (STE-18). The view keeps every row the registry holds and marks the
test-namespace ones with `is_test`; the route hides them unless `include_test`. The
scan goes through `skills.scan_registry`, so the filtered and the plain listing share
one `MAX_SCAN` cap and report the same `chain_total`.

Cost: one `query_all_skills` per scan page plus one `get_version` per audited skill,
overlapped (STE-33), at most once per TTL and only while requests arrive.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from sterish_pipeline.namespaces import is_test_skill_id

from . import chain, fanout, skills
from .config import settings


@dataclass(frozen=True)
class Row:
    skill_id: str
    owner: str
    registered_at: int
    version_count: int
    latest_version: str
    latest_audited_version: str | None
    verdict: str | None
    trust_score: int | None
    is_verified: bool | None
    # The latest audited version exists but could not be read. Not the same as
    # UNAUDITED, and never matched as such.
    read_failed: bool

    @property
    def is_test(self) -> bool:
        """Registered under a test namespace, hidden by default (STE-18)."""
        return is_test_skill_id(self.skill_id)

    @property
    def stale_audit(self) -> bool:
        """The newest version is not the audited one (including never audited)."""
        return self.latest_version != self.latest_audited_version

    def as_entry(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "owner": self.owner,
            "registered_at": self.registered_at,
            "versions": [None] * self.version_count,
            "latest_version": self.latest_version,
            "latest_audited_version": self.latest_audited_version,
        }


@dataclass(frozen=True)
class Snapshot:
    rows: tuple[Row, ...]
    built_at: float
    # get_skill_count() as read with these rows; always the real on-chain number.
    chain_total: int


_current: Snapshot | None = None
_generation = 0
_state_lock = threading.Lock()
_build_lock = threading.Lock()


def invalidate() -> None:
    """Drop the view. The next request rebuilds it from chain."""
    global _current, _generation
    with _state_lock:
        _current = None
        _generation += 1


def _fresh(snapshot: Snapshot | None) -> bool:
    return (
        snapshot is not None
        and time.time() - snapshot.built_at < settings.skills_snapshot_ttl_seconds
    )


def get() -> Snapshot:
    """The current view, rebuilding it if stale. One build at a time.

    A ChainError while building propagates (502 at the edge): an unreadable registry
    must never be served as an empty one.
    """
    with _state_lock:
        if _fresh(_current):
            return _current  # type: ignore[return-value]

    with _build_lock:
        with _state_lock:
            if _fresh(_current):
                return _current  # type: ignore[return-value]
            generation = _generation

        snapshot = _build()

        with _state_lock:
            # Invalidated while we were reading: this view may already be stale, so
            # serve it to the caller that waited for it but do not keep it.
            if _generation == generation:
                _set(snapshot)
        return snapshot


def _set(snapshot: Snapshot) -> None:
    global _current
    _current = snapshot


def _read_latest(entry: dict) -> tuple[dict | None, bool]:
    version = entry["latest_audited_version"]
    if not version:
        return None, False
    try:
        return chain.get_version(entry["skill_id"], version), False
    except chain.ContractError:
        return None, True


def _build() -> Snapshot:
    entries, chain_total = skills.scan_registry()

    results = fanout.map_bounded(_read_latest, entries, settings.chain_concurrency)

    rows = []
    for entry, (record, failed) in zip(entries, results, strict=True):
        rows.append(
            Row(
                skill_id=entry["skill_id"],
                owner=entry["owner"],
                registered_at=entry["registered_at"],
                version_count=len(entry["versions"]),
                latest_version=entry["latest_version"],
                latest_audited_version=entry["latest_audited_version"],
                verdict=record["verdict"] if record else None,
                trust_score=record["trust_score"] if record else None,
                is_verified=record["is_verified"] if record else None,
                read_failed=failed,
            )
        )
    return Snapshot(rows=tuple(rows), built_at=time.time(), chain_total=chain_total)
