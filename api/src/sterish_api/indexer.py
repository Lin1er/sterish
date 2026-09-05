"""Lightweight event indexer.

Tails the registry's `skill_registered` / `version_registered` / `version_recorded` /
`verdict_flipped` events into SQLite. Two jobs:

  1. supply the transaction hashes for the `evidence` object — the contract does not
     store them, so without this the tx links are permanently null;
  2. back the `/feed` activity endpoint the dashboard (STE-21) consumes.

**This cache is a cache, never a source of truth.** Every verdict-bearing response is
still read from the chain on request; the index only decorates it with tx links. Drop
the file and the API keeps answering correctly (proven by
tests/test_cache_is_not_source_of_truth.py). Rebuild: stop the API, delete the db,
start it again, or call `rebuild()`.

Operational note (measured against soroban-testnet 2026-09-04): `getEvents` scans only
a bounded window forward from `start_ledger` — a start 5_000 ledgers before a known
event still returned it, 10_000 before returned nothing. Asking once for the whole
retained range silently returns zero events, so the poller walks forward in chunks.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import threading
from typing import Any

from stellar_sdk import SorobanServer, scval
from stellar_sdk import xdr as stellar_xdr
from stellar_sdk.soroban_rpc import EventFilter, EventFilterType

from .chain import address_str, decode_verdict
from .config import settings

logger = logging.getLogger(__name__)

TRACKED_EVENTS = {
    "skill_registered",
    "version_registered",
    "version_recorded",
    "verdict_flipped",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event         TEXT    NOT NULL,
    skill_id      TEXT    NOT NULL,
    version       TEXT,
    content_hash  TEXT,
    verdict       TEXT,
    trust_score   INTEGER,
    owner         TEXT,
    auditor       TEXT,
    ledger        INTEGER NOT NULL,
    tx_hash       TEXT    NOT NULL,
    occurred_at   INTEGER,
    UNIQUE (event, skill_id, version, tx_hash)
);
CREATE INDEX IF NOT EXISTS idx_events_lookup  ON events (skill_id, version, event);
CREATE INDEX IF NOT EXISTS idx_events_ledger  ON events (ledger DESC, id DESC);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)


def rebuild() -> None:
    """Drop every indexed row and reset the cursor. The next poll refills from chain."""
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM meta WHERE key = 'last_indexed_ledger'")
    logger.info("indexer cache dropped; will rebuild from chain")


def _meta_get(key: str) -> str | None:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def _meta_set(key: str, value: str) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def last_indexed_ledger() -> int | None:
    raw = _meta_get("last_indexed_ledger")
    return int(raw) if raw else None


# --- reads used by the API layer -------------------------------------------


def tx_for(skill_id: str, version: str, event: str) -> str | None:
    """Newest transaction hash that emitted `event` for this exact version."""
    try:
        with _lock, _connect() as conn:
            row = conn.execute(
                "SELECT tx_hash FROM events WHERE skill_id = ? AND version = ? AND event = ? "
                "ORDER BY ledger DESC, id DESC LIMIT 1",
                (skill_id, version, event),
            ).fetchone()
            return row["tx_hash"] if row else None
    except sqlite3.Error as exc:
        # A broken cache must never break a chain-backed answer.
        logger.warning("index lookup failed (serving without tx links): %s", exc)
        return None


def feed(limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    try:
        with _lock, _connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
            rows = conn.execute(
                "SELECT * FROM events ORDER BY ledger DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows], int(total)
    except sqlite3.Error as exc:
        logger.warning("feed query failed: %s", exc)
        return [], 0


# --- polling ----------------------------------------------------------------


def _decode_event(ev: Any) -> dict | None:
    # Events emitted inside a contract call that ultimately failed are not facts about
    # the ledger state; indexing them would show phantom activity in the feed. Current
    # RPC only returns successful ones and has deprecated the flag for removal, so read
    # it out of __dict__ (no pydantic deprecation warning) and default to keeping the
    # event once the field is gone.
    if ev.__dict__.get("in_successful_contract_call", True) is False:
        return None

    topics = [scval.to_native(stellar_xdr.SCVal.from_xdr(t)) for t in ev.topic]
    if not topics:
        return None
    name = str(topics[0])
    if name not in TRACKED_EVENTS:
        return None

    value = scval.to_native(stellar_xdr.SCVal.from_xdr(ev.value))
    if not isinstance(value, dict):
        value = {}

    content_hash = value.get("content_hash")
    verdict_raw = value.get("verdict") or value.get("new_verdict")

    return {
        "event": name,
        "skill_id": str(topics[1]) if len(topics) > 1 else "",
        # Empty string, never NULL: SQLite treats NULLs as distinct in a UNIQUE
        # constraint, so a NULL version would let overlapping polls insert the same
        # skill_registered row twice. Served back as null by the feed.
        "version": str(topics[2]) if len(topics) > 2 else "",
        "content_hash": (
            bytes(content_hash).hex() if isinstance(content_hash, (bytes, bytearray)) else None
        ),
        "verdict": decode_verdict(verdict_raw) if verdict_raw is not None else None,
        "trust_score": int(value["trust_score"]) if value.get("trust_score") is not None else None,
        "owner": address_str(value.get("owner")),
        "auditor": address_str(value.get("auditor")),
        "ledger": int(ev.ledger),
        "tx_hash": ev.transaction_hash,
        "occurred_at": _ledger_time(ev),
    }


def _ledger_time(ev: Any) -> int | None:
    raw = getattr(ev, "ledger_close_at", None) or getattr(ev, "ledger_closed_at", None)
    if not raw:
        return None
    try:
        from datetime import datetime

        return int(datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return None


class _OutOfRange(Exception):
    """`start_ledger` is outside the RPC's retained range. Carries the new lower bound."""

    def __init__(self, message: str, oldest: int | None):
        super().__init__(message)
        self.oldest = oldest


_RANGE_RE = re.compile(r"ledger range:\s*(\d+)\s*-\s*(\d+)")


def _get_events(server: SorobanServer, start: int):
    """One getEvents call, translating the retention-window error into _OutOfRange."""
    try:
        return server.get_events(
            start_ledger=start,
            filters=[
                EventFilter(
                    event_type=EventFilterType.CONTRACT,
                    contract_ids=[settings.registry_contract_id],
                )
            ],
            limit=200,
        )
    except Exception as exc:
        match = _RANGE_RE.search(str(exc))
        if match:
            raise _OutOfRange(str(exc), int(match.group(1))) from exc
        raise


def _store(rows: list[dict]) -> int:
    if not rows:
        return 0
    with _lock, _connect() as conn:
        cur = conn.executemany(
            "INSERT OR IGNORE INTO events "
            "(event, skill_id, version, content_hash, verdict, trust_score, owner, auditor, "
            " ledger, tx_hash, occurred_at) "
            "VALUES (:event, :skill_id, :version, :content_hash, :verdict, :trust_score, "
            "        :owner, :auditor, :ledger, :tx_hash, :occurred_at)",
            rows,
        )
        return cur.rowcount or 0


def poll_once() -> int:
    """One catch-up pass. Returns how many new rows were stored."""
    if not settings.registry_contract_id:
        return 0

    server = SorobanServer(settings.rpc_url)
    try:
        health = server.get_health()
        latest = server.get_latest_ledger().sequence
    except Exception as exc:
        logger.warning("indexer: RPC unreachable: %s", exc)
        return 0

    cursor = last_indexed_ledger()
    if cursor is None:
        # First run: start at the oldest ledger the RPC still retains, so the whole
        # available history is indexed rather than only what happens from now on.
        cursor = int(getattr(health, "oldest_ledger", None) or max(latest - 1, 1))

    stored = 0
    chunk = max(1, settings.indexer_chunk_ledgers)
    start = cursor

    while start <= latest:
        try:
            res = _get_events(server, start)
        except _OutOfRange as exc:
            # The retention window slid past our cursor while we were walking it
            # (ledgers close every ~5s). Jump to the oldest ledger still served and
            # carry on; the skipped range is simply no longer available from RPC.
            if exc.oldest is None or exc.oldest <= start:
                logger.warning("indexer: cannot recover ledger range at %s: %s", start, exc)
                break
            logger.info(
                "indexer: cursor %s fell out of retention, resuming at %s", start, exc.oldest
            )
            start = exc.oldest
            continue
        except Exception as exc:
            logger.warning("indexer: getEvents at %s failed: %s", start, exc)
            break

        rows = [r for r in (_decode_event(e) for e in res.events) if r]
        stored += _store(rows)
        start = min(start + chunk, latest + 1)
        _meta_set("last_indexed_ledger", str(min(start - 1, latest)))

    if stored:
        logger.info("indexer: stored %s new event rows (through ledger %s)", stored, latest)
    return stored


async def run_forever() -> None:
    init_db()
    while True:
        try:
            await asyncio.to_thread(poll_once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a crashed poller must not take the API down
            logger.warning("indexer loop error: %s", exc)
        await asyncio.sleep(settings.indexer_poll_seconds)
