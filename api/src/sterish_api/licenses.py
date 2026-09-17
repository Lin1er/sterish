"""Every licence one address holds (STE-46), read from the tokens contract.

**Why not simply the event index.** The ticket suggested tailing `license_minted`. That
alone would be wrong in the same way STE-34 found for `/skills`: `getEvents` only reaches
back as far as the RPC node retains events (about a week on testnet), so an index rebuilt
today silently lacks every licence minted before that window, and an address that paid a
month ago would be told it holds nothing. Deleting the cache must never change an answer.

So the list comes from the contract's own enumeration: `total_supply()` then
`get_token(id)` for ids 1..total_supply. Tokens are soulbound and never burned, so a
record, once read, is true forever — it is cached by id and only the ids minted since the
last request are read. Every request still reads `total_supply` live, so the list is
complete up to the current ledger, never up to whenever the cache was last filled.

`license_minted` events are still tailed (indexer.py), but only to decorate a licence with
the transaction that minted it; a licence older than the event window is listed with
`mint_tx: null`, never left out.

A read that fails is raised, never served as a shorter list (api-spec §6).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from typing import Any

from . import chain, fanout
from .config import settings

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    tokens_contract_id  TEXT    NOT NULL,
    token_id            INTEGER NOT NULL,
    kind                TEXT    NOT NULL,
    skill_id            TEXT    NOT NULL,
    version             TEXT    NOT NULL,
    owner               TEXT    NOT NULL,
    minted_at           INTEGER NOT NULL,
    PRIMARY KEY (tokens_contract_id, token_id)
);
CREATE INDEX IF NOT EXISTS idx_tokens_owner ON tokens (tokens_contract_id, owner, kind);
CREATE TABLE IF NOT EXISTS license_events (
    tokens_contract_id  TEXT    NOT NULL,
    agent               TEXT    NOT NULL,
    skill_id            TEXT    NOT NULL,
    version             TEXT    NOT NULL,
    ledger              INTEGER NOT NULL,
    tx_hash             TEXT    NOT NULL,
    occurred_at         INTEGER,
    UNIQUE (tokens_contract_id, agent, skill_id, version, tx_hash)
);
CREATE INDEX IF NOT EXISTS idx_license_events ON license_events
    (tokens_contract_id, agent, skill_id, version);
"""

_db_lock = threading.Lock()
# One sync at a time: two page loads racing would otherwise both read the same new ids.
_sync_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db_lock, _connect() as conn:
        conn.executescript(_SCHEMA)


def _known_ids(contract: str) -> set[int]:
    with _db_lock, _connect() as conn:
        conn.executescript(_SCHEMA)
        rows = conn.execute(
            "SELECT token_id FROM tokens WHERE tokens_contract_id = ?", (contract,)
        ).fetchall()
        return {int(r["token_id"]) for r in rows}


def _store_tokens(contract: str, records: list[dict]) -> None:
    with _db_lock, _connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO tokens "
            "(tokens_contract_id, token_id, kind, skill_id, version, owner, minted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (contract, r["token_id"], r["kind"], r["skill_id"], r["version"],
                 r["owner"], r["minted_at"])
                for r in records
            ],
        )


def sync() -> int:
    """Bring the token cache up to the live `total_supply`. Returns that supply.

    Reads every id not yet cached, including gaps a crashed earlier sync left behind.
    Raises `chain.ChainError` if any of them cannot be read.
    """
    contract = settings.tokens_contract_id
    if not contract:
        raise chain.NotConfiguredError("TOKENS_CONTRACT_ID (or TOKENS_CA) is not set")

    with _sync_lock:
        supply = chain.total_supply()
        missing = sorted(set(range(1, supply + 1)) - _known_ids(contract))
        if not missing:
            return supply

        def read(token_id: int) -> dict:
            try:
                return chain.get_token(token_id)
            except chain.ContractError as exc:
                # An id at or below total_supply that the contract cannot return is not
                # "no such licence"; it is a read we could not complete.
                raise chain.ChainError(
                    f"get_token({token_id}) failed below total_supply {supply}: {exc}"
                ) from exc

        records = fanout.map_bounded(read, missing, settings.chain_concurrency)
        _store_tokens(contract, records)
        logger.info("licences: cached %s new token records (supply %s)", len(records), supply)
        return supply


def record_license_event(row: dict[str, Any]) -> None:
    """Store one decoded `license_minted` event (called by the indexer)."""
    with _db_lock, _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO license_events "
            "(tokens_contract_id, agent, skill_id, version, ledger, tx_hash, occurred_at) "
            "VALUES (:tokens_contract_id, :agent, :skill_id, :version, :ledger, :tx_hash, "
            "        :occurred_at)",
            row,
        )


def for_agent(agent: str) -> list[dict[str, Any]]:
    """Licences held by `agent` on the configured tokens contract, newest first.

    Call `sync()` first; this reads the cache it filled.
    """
    contract = settings.tokens_contract_id
    with _db_lock, _connect() as conn:
        conn.executescript(_SCHEMA)
        rows = conn.execute(
            "SELECT t.token_id, t.skill_id, t.version, t.minted_at, "
            "       (SELECT e.tx_hash FROM license_events e "
            "         WHERE e.tokens_contract_id = t.tokens_contract_id AND e.agent = t.owner "
            "           AND e.skill_id = t.skill_id AND e.version = t.version "
            "         ORDER BY e.ledger DESC LIMIT 1) AS mint_tx "
            "FROM tokens t "
            "WHERE t.tokens_contract_id = ? AND t.owner = ? AND t.kind = 'LICENSE' "
            "ORDER BY t.minted_at DESC, t.token_id DESC",
            (contract, agent),
        ).fetchall()
        return [dict(r) for r in rows]
