"""Read-only Soroban client for the SkillRegistry contract.

Every read is a `simulateTransaction` against a throwaway source account: the API
holds no keys and needs no funded account (verified against soroban-testnet,
2026-09-04). Replaces the scaffold's hand-rolled JSON-RPC payload, which was not a
valid Soroban request and never returned real data.

Decoding notes, all confirmed against the live contract rather than assumed:
  * a `#[contracttype]` struct decodes to a dict keyed by field name;
  * a `#[contracttype]` enum unit variant decodes to a ONE-ELEMENT LIST,
    e.g. `AuditVerdict::Safe` -> `['Safe']`;
  * `BytesN<32>` decodes to `bytes`, `Address` to an Address object;
  * `Option::None` decodes to `None`;
  * a contract `Err(...)` surfaces as `sim.error` text containing
    `Error(Contract, #N)`, not as an exception.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from stellar_sdk import Account, SorobanServer, TransactionBuilder, scval
from stellar_sdk import xdr as stellar_xdr

from .config import settings

logger = logging.getLogger(__name__)

# Simulation never submits, so the source account only has to parse as a valid
# ed25519 public key. It deliberately does not exist on the ledger.
NULL_ACCOUNT = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"

_ZERO_HASH = bytes(32)
_CONTRACT_ERR_RE = re.compile(r"Error\(Contract, #(\d+)\)")


class ChainError(Exception):
    """RPC was unreachable or returned something unusable -> 502."""


class ContractError(Exception):
    """The contract returned a typed Err(...). `code` is the frozen ABI number."""

    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message or f"contract error #{code}")
        self.code = code


class NotConfiguredError(Exception):
    """REGISTRY_CONTRACT_ID / REGISTRY_CA is unset -> 503."""


def _server() -> SorobanServer:
    return SorobanServer(settings.rpc_url)


def _invoke(function: str, args: list) -> Any:
    """Simulate a read-only contract call and return the decoded native value."""
    if not settings.registry_contract_id:
        raise NotConfiguredError("REGISTRY_CONTRACT_ID (or REGISTRY_CA) is not set")

    try:
        tx = (
            TransactionBuilder(Account(NULL_ACCOUNT, 0), settings.network_passphrase, base_fee=100)
            .add_time_bounds(0, 0)
            .append_invoke_contract_function_op(settings.registry_contract_id, function, args)
            .build()
        )
        sim = _server().simulate_transaction(tx)
    except Exception as exc:  # network failure, malformed response, ...
        logger.warning("RPC call %s failed: %s", function, exc)
        raise ChainError(f"RPC call to {function} failed: {exc}") from exc

    if sim.error:
        match = _CONTRACT_ERR_RE.search(str(sim.error))
        if match:
            raise ContractError(int(match.group(1)), str(sim.error))
        # Not a typed contract error: a host/RPC level problem.
        raise ChainError(f"simulation of {function} failed: {sim.error}")

    if not sim.results:
        raise ChainError(f"simulation of {function} returned no results")

    return scval.to_native(stellar_xdr.SCVal.from_xdr(sim.results[0].xdr))


# --- decoding helpers -------------------------------------------------------


def decode_verdict(raw: Any) -> str:
    """`['Safe']` -> `'SAFE'`. Anything unrecognised is reported as UNAUDITED.

    Guessing SAFE for an unknown encoding would be the single worst failure mode
    this service has, so the fallback is deliberately the most conservative value.
    """
    if isinstance(raw, (list, tuple)) and raw:
        raw = raw[0]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    name = str(raw).upper()
    return name if name in {"SAFE", "DANGEROUS", "WARNING", "UNAUDITED"} else "UNAUDITED"


def _hex_or_none(raw: Any) -> str | None:
    """Hex-encode a 32-byte field; an all-zero hash means 'not set' -> None."""
    if not isinstance(raw, (bytes, bytearray)):
        return None
    if bytes(raw) == _ZERO_HASH:
        return None
    return bytes(raw).hex()


def address_str(raw: Any) -> str | None:
    """Render an Address as its `G…`/`C…` strkey.

    `str(Address)` returns the debug repr (`<Address [type=ACCOUNT, address=G…]>`),
    not the strkey, so go through `.address` and fall back only if it is absent.
    """
    if raw is None:
        return None
    return getattr(raw, "address", None) or str(raw)


def decode_version_record(raw: dict) -> dict:
    """Normalise an on-chain VersionRecord into the shape the API layer serves."""
    verdict = decode_verdict(raw.get("verdict"))
    audited_at = int(raw.get("audited_at") or 0)
    return {
        "skill_id": raw.get("skill_id", ""),
        "version": raw.get("version", ""),
        "content_hash": bytes(raw["content_hash"]).hex() if raw.get("content_hash") else "",
        "verdict": verdict,
        "trust_score": int(raw.get("trust_score") or 0),
        "is_verified": verdict == "SAFE",
        "owner": address_str(raw.get("owner")) or "",
        # `auditor` and `audited_at` are only meaningful once a verdict exists; the
        # contract leaves them zero-valued while UNAUDITED and the spec wants null.
        "auditor": address_str(raw.get("auditor")) if verdict != "UNAUDITED" else None,
        "registered_at": int(raw.get("registered_at") or 0),
        "audited_at": audited_at or None,
        "evidence_hash": _hex_or_none(raw.get("evidence_hash")),
    }


def decode_skill_entry(raw: dict) -> dict:
    return {
        "skill_id": raw.get("skill_id", ""),
        "owner": address_str(raw.get("owner")) or "",
        "versions": [str(v) for v in (raw.get("versions") or [])],
        "latest_version": raw.get("latest_version", ""),
        "latest_audited_version": raw.get("latest_audited_version"),
        "registered_at": int(raw.get("registered_at") or 0),
    }


# --- contract reads ---------------------------------------------------------


def lookup_by_hash(content_hash_hex: str) -> dict | None:
    """`lookup_by_hash(BytesN<32>) -> Option<VersionRecord>`. None means unregistered."""
    raw = _invoke("lookup_by_hash", [scval.to_bytes(bytes.fromhex(content_hash_hex))])
    return None if raw is None else decode_version_record(raw)


def get_version(skill_id: str, version: str) -> dict:
    """`get_version(String, String) -> VersionRecord`. Raises ContractError 3/4 on a miss."""
    raw = _invoke("get_version", [scval.to_string(skill_id), scval.to_string(version)])
    return decode_version_record(raw)


def query_skill(skill_id: str) -> dict:
    """`query_skill(String) -> SkillEntry`. Raises ContractError 3 when unknown."""
    return decode_skill_entry(_invoke("query_skill", [scval.to_string(skill_id)]))


def query_all_skills(start: int, limit: int) -> list[dict]:
    raw = _invoke("query_all_skills", [scval.to_uint32(start), scval.to_uint32(limit)])
    return [decode_skill_entry(entry) for entry in (raw or [])]


def get_skill_count() -> int:
    return int(_invoke("get_skill_count", []) or 0)


def rpc_reachable() -> tuple[bool, int | None]:
    """Used by /health. Returns (reachable, latest_ledger)."""
    try:
        return True, _server().get_latest_ledger().sequence
    except Exception as exc:
        logger.warning("RPC health probe failed: %s", exc)
        return False, None
