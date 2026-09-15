"""Settled payments that are owed a licence (STE-42).

**This is not a cache.** The indexer's SQLite file can be deleted at any time because
every row in it can be read back from the chain. Nothing here can: a settlement the
facilitator confirmed is money that has already moved, and the only record that it
is still owed a licence is this table. Keep it on its own volume and never delete it
as part of an index rebuild.

The table exists for one failure. `/use` settles the payment and then mints the
licence. Those are two transactions, and the second can fail or time out after the
first has landed. Before this table existed that left a buyer who had paid with no
licence and no way back: retrying the same payment is refused, because it is
already settled, and a new payment charges them twice. So the settlement is written
here before the mint is attempted, and the next request from that payer finishes
the mint instead of asking for money again.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    payer       TEXT    NOT NULL,
    skill_id    TEXT    NOT NULL,
    version     TEXT    NOT NULL,
    settle_tx   TEXT    NOT NULL UNIQUE,
    amount      TEXT    NOT NULL,
    settled_at  INTEGER NOT NULL,
    mint_tx     TEXT,
    minted_at   INTEGER,
    last_error  TEXT
);
CREATE INDEX IF NOT EXISTS idx_payments_owed ON payments (payer, skill_id, version, minted_at);
"""

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.payments_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)


def record_settlement(
    payer: str, skill_id: str, version: str, settle_tx: str, amount: str
) -> None:
    """Record money that moved, before anything else can fail.

    Idempotent on the settlement hash: the same settlement recorded twice is one row.
    """
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO payments "
            "(payer, skill_id, version, settle_tx, amount, settled_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (payer, skill_id, version, settle_tx, amount, int(time.time())),
        )


def owed(payer: str, skill_id: str, version: str) -> dict[str, Any] | None:
    """The oldest settlement for this exact licence that has not been minted yet."""
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM payments WHERE payer = ? AND skill_id = ? AND version = ? "
            "AND minted_at IS NULL ORDER BY id LIMIT 1",
            (payer, skill_id, version),
        ).fetchone()
        return dict(row) if row else None


def mark_minted(settle_tx: str, mint_tx: str | None) -> None:
    """Close out a settlement. `mint_tx` is None when the licence was found already
    on chain — a mint that landed although its confirmation never reached us."""
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE payments SET mint_tx = ?, minted_at = ?, last_error = NULL "
            "WHERE settle_tx = ?",
            (mint_tx, int(time.time()), settle_tx),
        )


def mark_error(settle_tx: str, error: str) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE payments SET last_error = ? WHERE settle_tx = ?",
            (error[:500], settle_tx),
        )


def get(settle_tx: str) -> dict[str, Any] | None:
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM payments WHERE settle_tx = ?", (settle_tx,)
        ).fetchone()
        return dict(row) if row else None
