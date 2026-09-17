"""Proof that the caller controls the address it claims (STE-48).

`GET /use` serves an already-licensed artifact for free. Before STE-48 "already
licensed" was decided by `X-AGENT-ADDRESS` alone, and licence holders are public on
chain, so anyone could name a holder's address and receive what that holder paid
for. A soulbound licence that anyone can borrow is not soulbound.

The free path now needs a signature from the address's own key over a short-lived,
single-use challenge the API issued:

1. `GET /use/{skill_id}/{version}/challenge?agent=G...` issues a nonce and returns the
   exact message to sign.
2. The caller signs it with **SEP-53** — ed25519 over
   `SHA-256("Stellar Signed Message:\\n" + message)` — which is what a wallet's SEP-43
   `signMessage` produces and what `stellar message sign` produces.
3. The caller repeats `GET /use/...` with `X-AGENT-ADDRESS`, `X-STERISH-PROOF-NONCE` and
   `X-STERISH-PROOF-SIGNATURE` (base64).

The message is rebuilt here from the stored row, never taken from the request, so a
client cannot get a different text accepted. A nonce is bound to one agent, one skill
and one version, expires, and is consumed by the first request that proves with it.
A failed signature does not consume it: otherwise anyone who guessed a nonce could
burn another caller's challenge, and a nonce is 128 random bits, so guessing is not a
path to anything else.

Stored in the payments database file (its own table): the rows must survive a
restart, or a nonce used just before one could be replayed just after.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any

from stellar_sdk import Keypair
from stellar_sdk.exceptions import BadSignatureError

from .config import settings

SEP53_PREFIX = b"Stellar Signed Message:\n"
MESSAGE_TITLE = "Sterish licence ownership proof"

NONCE_HEADER = "X-STERISH-PROOF-NONCE"
SIGNATURE_HEADER = "X-STERISH-PROOF-SIGNATURE"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS proof_challenges (
    nonce       TEXT    PRIMARY KEY,
    agent       TEXT    NOT NULL,
    skill_id    TEXT    NOT NULL,
    version     TEXT    NOT NULL,
    issued_at   INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL,
    used_at     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_proof_expiry ON proof_challenges (expires_at);
"""

# Rows past expiry are kept this long before being purged, so a replay of a recently
# used nonce is still reported as "already used" rather than "unknown".
_PURGE_GRACE_SECONDS = 3600

_lock = threading.Lock()


class ProofInvalid(Exception):
    """The proof was supplied and is wrong. `reason` is safe to return to the caller."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Challenge:
    agent: str
    skill_id: str
    version: str
    nonce: str
    issued_at: int
    expires_at: int

    @property
    def message(self) -> str:
        return build_message(
            self.agent, self.skill_id, self.version, self.nonce, self.expires_at
        )


def build_message(agent: str, skill_id: str, version: str, nonce: str, expires_at: int) -> str:
    """The exact text a caller signs. Frozen: changing it invalidates every client.

    The network passphrase is in the text so a proof made for testnet can never be
    mistaken for one made against a mainnet deployment of the same API.
    """
    return "\n".join(
        [
            MESSAGE_TITLE,
            f"agent: {agent}",
            f"skill: {skill_id}",
            f"version: {version}",
            f"nonce: {nonce}",
            f"expires: {expires_at}",
            f"network: {settings.network_passphrase}",
        ]
    )


def sep53_digest(message: str) -> bytes:
    return hashlib.sha256(SEP53_PREFIX + message.encode("utf-8")).digest()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.payments_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def init_db() -> None:
    with _lock, _connect():
        pass


def issue(agent: str, skill_id: str, version: str, *, now: int | None = None) -> Challenge:
    now = int(time.time()) if now is None else now
    challenge = Challenge(
        agent=agent,
        skill_id=skill_id,
        version=version,
        nonce=secrets.token_hex(16),
        issued_at=now,
        expires_at=now + settings.proof_ttl_seconds,
    )
    with _lock, _connect() as conn:
        conn.execute(
            "DELETE FROM proof_challenges WHERE expires_at < ?", (now - _PURGE_GRACE_SECONDS,)
        )
        conn.execute(
            "INSERT INTO proof_challenges "
            "(nonce, agent, skill_id, version, issued_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                challenge.nonce, agent, skill_id, version,
                challenge.issued_at, challenge.expires_at,
            ),
        )
    return challenge


def _get(nonce: str) -> dict[str, Any] | None:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM proof_challenges WHERE nonce = ?", (nonce,)).fetchone()
        return dict(row) if row else None


def _decode_signature(raw: str) -> bytes:
    value = raw.strip()
    try:
        # Accept both base64 alphabets; wallets differ. Padding is restored first.
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.b64decode(padded.replace("-", "+").replace("_", "/"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProofInvalid("signature is not base64") from exc
    if len(decoded) != 64:
        raise ProofInvalid(f"signature must be 64 bytes (ed25519), got {len(decoded)}")
    return decoded


def verify_and_consume(
    agent: str,
    skill_id: str,
    version: str,
    nonce: str,
    signature: str,
    *,
    now: int | None = None,
) -> None:
    """Accept the proof exactly once, or raise ProofInvalid naming why."""
    now = int(time.time()) if now is None else now
    nonce = nonce.strip()
    row = _get(nonce)
    if row is None:
        raise ProofInvalid("unknown nonce; request a new challenge")
    if row["agent"] != agent:
        raise ProofInvalid("this challenge was issued for a different agent")
    if row["skill_id"] != skill_id or row["version"] != version:
        raise ProofInvalid("this challenge was issued for a different skill or version")
    if row["used_at"] is not None:
        raise ProofInvalid("this challenge has already been used; request a new one")
    if now > row["expires_at"]:
        raise ProofInvalid("this challenge has expired; request a new one")

    sig = _decode_signature(signature)
    message = build_message(agent, skill_id, version, nonce, row["expires_at"])
    try:
        Keypair.from_public_key(agent).verify(sep53_digest(message), sig)
    except BadSignatureError as exc:
        raise ProofInvalid(
            "signature does not verify against the agent's key "
            "(expected SEP-53 over the challenge message)"
        ) from exc

    # Conditional update: of two requests racing with the same valid proof, one wins.
    with _lock, _connect() as conn:
        consumed = conn.execute(
            "UPDATE proof_challenges SET used_at = ? "
            "WHERE nonce = ? AND used_at IS NULL AND expires_at >= ?",
            (now, nonce, now),
        ).rowcount
    if consumed != 1:
        raise ProofInvalid("this challenge has already been used; request a new one")
