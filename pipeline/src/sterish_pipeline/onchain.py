"""Soroban contract access for the audit orchestrator.

Replaces the scaffold module wholesale. That version could not even be imported
(`from stellar_sdk.contract import Contract` — the module exports no `Contract`),
used `Server` (Horizon, which has neither `prepare_transaction` nor
`simulate_transaction`) and called `submit_verdict` with four arguments and the
verdict as a `u32`. Nothing imported it, so none of that had ever run.

Every encoding below was proven against the deployed registry by simulation
rather than inferred from documentation:

    5 args, verdict as vec[symbol]  -> Error(Contract, #3)   accepted, business logic
    4 args, verdict as u32          -> Error(WasmVm, UnexpectedSize)
    5 args, verdict as u32          -> Error(WasmVm, InvalidAction)
    5 args, verdict as bare symbol  -> Error(WasmVm, InvalidAction)

Reaching a *contract* error means the host accepted the argument shape; a WasmVm
error means it never got that far. Hence `vec[symbol]` for a unit enum variant.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from stellar_sdk import Account, Address, Keypair, SorobanServer, TransactionBuilder, scval
from stellar_sdk import xdr as stellar_xdr
from stellar_sdk.soroban_rpc import GetTransactionStatus, SendTransactionStatus

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import FinalVerdict

logger = logging.getLogger(__name__)

# Reads simulate from a throwaway account that does not exist on the ledger, so
# querying needs no key and no funded account.
NULL_ACCOUNT = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"

_CONTRACT_ERR_RE = re.compile(r"Error\(Contract, #(\d+)\)")

# contracts/registry/src/data.rs — part of the frozen ABI, never renumber.
REGISTRY_ERRORS = {
    1: "NotInitialized", 2: "NotAuthorized", 3: "SkillNotFound",
    4: "VersionNotFound", 5: "VersionAlreadyExists", 6: "HashAlreadyRegistered",
    7: "InvalidInput", 8: "InvalidTrustScore", 9: "InvalidVerdict",
}


class OnChainError(Exception):
    """RPC unreachable, transaction rejected, or timed out."""


class ContractCallError(OnChainError):
    """The contract returned a typed Err(...). `code` is the frozen ABI number."""

    def __init__(self, code: int, function: str, raw: str = ""):
        name = REGISTRY_ERRORS.get(code, "Unknown")
        super().__init__(f"{function} failed: {name} (#{code})")
        self.code = code
        self.function = function
        self.raw = raw


@dataclass(frozen=True)
class TxResult:
    tx_hash: str
    value: Any = None

    def url(self, network: str = "testnet") -> str:
        return f"https://stellar.expert/explorer/{network}/tx/{self.tx_hash}"


def _server(cfg: PipelineConfig) -> SorobanServer:
    return SorobanServer(cfg.rpc_url)


def _decode(xdr_str: str) -> Any:
    return scval.to_native(stellar_xdr.SCVal.from_xdr(xdr_str))


def _raise_for_error(error: Any, function: str) -> None:
    match = _CONTRACT_ERR_RE.search(str(error))
    if match:
        raise ContractCallError(int(match.group(1)), function, str(error))
    raise OnChainError(f"{function} simulation failed: {error}")


# --- encoding ---------------------------------------------------------------


def verdict_scval(verdict: FinalVerdict | str) -> stellar_xdr.SCVal:
    """Encode `AuditVerdict` — a unit enum variant is a one-element vec of symbols.

    A bare symbol or a u32 is rejected by the host with `InvalidAction`; see the
    module docstring for the full evidence table.
    """
    name = verdict.value if isinstance(verdict, FinalVerdict) else str(verdict)
    variant = name.strip().capitalize()  # SAFE -> Safe, matching the Rust variant
    if variant not in {"Unaudited", "Safe", "Dangerous", "Warning"}:
        raise ValueError(f"not an AuditVerdict variant: {name!r}")
    return scval.to_vec([scval.to_symbol(variant)])


def hash_scval(hex_hash: str) -> stellar_xdr.SCVal:
    """Encode a `BytesN<32>`; rejects the wrong width here rather than on-chain."""
    raw = bytes.fromhex(hex_hash)
    if len(raw) != 32:
        raise ValueError(f"expected 32 bytes, got {len(raw)}")
    return scval.to_bytes(raw)


# --- reads ------------------------------------------------------------------


def simulate(cfg: PipelineConfig, contract_id: str, function: str, args: list | None = None) -> Any:
    """Read-only contract call. Returns the decoded native value."""
    try:
        tx = (
            TransactionBuilder(Account(NULL_ACCOUNT, 0), cfg.network_passphrase, base_fee=100)
            .add_time_bounds(0, 0)
            .append_invoke_contract_function_op(contract_id, function, args or [])
            .build()
        )
        sim = _server(cfg).simulate_transaction(tx)
    except Exception as exc:
        raise OnChainError(f"RPC call to {function} failed: {exc}") from exc

    if sim.error:
        _raise_for_error(sim.error, function)
    if not sim.results:
        return None
    return _decode(sim.results[0].xdr)


# --- writes -----------------------------------------------------------------


def invoke(
    cfg: PipelineConfig,
    contract_id: str,
    function: str,
    args: list,
    signer_secret: str,
    *,
    timeout_s: int = 60,
    retries: int = 3,
) -> TxResult:
    """Sign, submit and confirm one contract call. Returns the transaction hash.

    Retries only transport-level failures. A `ContractCallError` is a decision the
    contract made and is never retried — resubmitting it would either fail
    identically or, worse, double-apply a call that actually succeeded.
    """
    keypair = Keypair.from_secret(signer_secret)
    last: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            return _invoke_once(
                cfg, contract_id, function, args, keypair, timeout_s=timeout_s
            )
        except ContractCallError:
            raise
        except OnChainError as exc:
            last = exc
            if attempt < retries:
                backoff = 2 ** (attempt - 1)
                logger.warning(
                    "%s attempt %s/%s failed (%s); retrying in %ss",
                    function, attempt, retries, exc, backoff,
                )
                time.sleep(backoff)

    raise OnChainError(f"{function} failed after {retries} attempts: {last}")


def _prepare_error_detail(exc: Exception) -> str:
    """Best-effort extraction of the simulation error behind an SDK exception."""
    for attr in ("simulate_transaction_response", "response"):
        response = getattr(exc, attr, None)
        error = getattr(response, "error", None)
        if error:
            return str(error)
    return str(exc)


def _invoke_once(
    cfg: PipelineConfig,
    contract_id: str,
    function: str,
    args: list,
    keypair: Keypair,
    *,
    timeout_s: int,
) -> TxResult:
    server = _server(cfg)

    try:
        source = server.load_account(keypair.public_key)
        tx = (
            TransactionBuilder(source, cfg.network_passphrase, base_fee=1_000_000)
            .add_time_bounds(0, 0)
            .append_invoke_contract_function_op(contract_id, function, args)
            .build()
        )
        # prepare_transaction simulates and attaches the footprint, resource fees and
        # auth entries. It raises on a contract error, which is why it is inside the
        # try and translated below rather than left as an SDK-specific exception.
        prepared = server.prepare_transaction(tx)
    except Exception as exc:
        # prepare_transaction raises with a generic message ("Simulation transaction
        # failed...") and keeps the detail on the attached response. Without digging
        # it out, a contract rejection looks like a transport fault and gets retried
        # three times for nothing.
        detail = _prepare_error_detail(exc)
        match = _CONTRACT_ERR_RE.search(detail)
        if match:
            raise ContractCallError(int(match.group(1)), function, detail) from exc
        raise OnChainError(f"preparing {function} failed: {detail}") from exc

    prepared.sign(keypair)

    try:
        sent = server.send_transaction(prepared)
    except Exception as exc:
        raise OnChainError(f"submitting {function} failed: {exc}") from exc

    if sent.status == SendTransactionStatus.ERROR:
        raise OnChainError(f"{function} rejected at submit: {sent.error_result_xdr}")
    if sent.status == SendTransactionStatus.TRY_AGAIN_LATER:
        raise OnChainError(f"{function} throttled by RPC (TRY_AGAIN_LATER)")

    return _await_tx(server, sent.hash, function, timeout_s=timeout_s)


def _return_value(got: Any, function: str) -> Any:
    """Decode the contract's return value from the transaction meta.

    The meta is versioned and the soroban payload moved: testnet currently returns
    **v4**, and reading only `meta.v3` silently yields None. That is not a harmless
    miss -- the escrow orchestration used the returned request_id, and falling back
    to a guess made it bond against somebody else's request. So every known version
    is tried and a failure to decode is logged, never swallowed.
    """
    if not getattr(got, "result_meta_xdr", None):
        return None
    try:
        meta = stellar_xdr.TransactionMeta.from_xdr(got.result_meta_xdr)
    except Exception as exc:
        logger.warning("%s: could not parse transaction meta: %s", function, exc)
        return None

    for version in ("v4", "v3"):
        container = getattr(meta, version, None)
        soroban = getattr(container, "soroban_meta", None) if container is not None else None
        raw = getattr(soroban, "return_value", None) if soroban is not None else None
        if raw is not None:
            try:
                return scval.to_native(raw)
            except Exception as exc:
                logger.warning("%s: could not decode return value: %s", function, exc)
                return None

    logger.debug("%s: transaction meta carried no return value", function)
    return None


def _await_tx(server: SorobanServer, tx_hash: str, function: str, *, timeout_s: int) -> TxResult:
    """Poll until the transaction is final. A timeout is reported as such, never as
    a failure: the transaction may still land, and the caller's journal must be able
    to tell "unknown" apart from "definitely did not happen"."""
    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        try:
            got = server.get_transaction(tx_hash)
        except Exception as exc:
            raise OnChainError(f"polling {function} ({tx_hash}) failed: {exc}") from exc

        if got.status == GetTransactionStatus.SUCCESS:
            logger.info("%s succeeded: %s", function, tx_hash)
            return TxResult(tx_hash=tx_hash, value=_return_value(got, function))

        if got.status == GetTransactionStatus.FAILED:
            raise OnChainError(f"{function} failed on-chain: {tx_hash}")

        time.sleep(1)

    raise OnChainError(
        f"{function} ({tx_hash}) did not finalise within {timeout_s}s; "
        "state is UNKNOWN, re-check before resubmitting"
    )


# --- typed contract calls ---------------------------------------------------


def lookup_by_hash(cfg: PipelineConfig, registry_id: str, content_hash: str) -> dict | None:
    """`Option<VersionRecord>`; None means these bytes are not registered."""
    return simulate(cfg, registry_id, "lookup_by_hash", [hash_scval(content_hash)])


def is_verified(cfg: PipelineConfig, registry_id: str, skill_id: str, version: str) -> bool:
    return bool(simulate(cfg, registry_id, "is_verified",
                         [scval.to_string(skill_id), scval.to_string(version)]))


def register_skill(cfg, registry_id, owner_secret, skill_id, version, content_hash) -> TxResult:
    """Signed by the skill owner."""
    owner = Keypair.from_secret(owner_secret).public_key
    return invoke(cfg, registry_id, "register_skill", [
        scval.to_address(Address(owner)),
        scval.to_string(skill_id),
        scval.to_string(version),
        hash_scval(content_hash),
    ], owner_secret)


def submit_verdict(cfg, registry_id, auditor_secret, skill_id, version,
                   verdict, score, evidence_hash) -> TxResult:
    """Signed by the registry's stored auditor. Five arguments, verdict as an enum."""
    return invoke(cfg, registry_id, "submit_verdict", [
        scval.to_string(skill_id),
        scval.to_string(version),
        verdict_scval(verdict),
        scval.to_uint32(int(score)),
        hash_scval(evidence_hash),
    ], auditor_secret)


def mint_verified(cfg, tokens_id, auditor_secret, skill_id, version, owner) -> TxResult:
    """Signed by the tokens contract's auditor role. Gated on-chain by
    `registry.is_verified`, so a DANGEROUS version can never receive a badge."""
    return invoke(cfg, tokens_id, "mint_verified", [
        scval.to_string(skill_id),
        scval.to_string(version),
        scval.to_address(Address(owner)),
    ], auditor_secret)


def create_audit_request(cfg, escrow_id, requestor_secret, skill_id, version,
                         fee_amount, bond_amount) -> TxResult:
    requestor = Keypair.from_secret(requestor_secret).public_key
    return invoke(cfg, escrow_id, "create_audit_request", [
        scval.to_address(Address(requestor)),
        scval.to_string(skill_id),
        scval.to_string(version),
        scval.to_int128(int(fee_amount)),
        scval.to_int128(int(bond_amount)),
    ], requestor_secret)


def post_bond(cfg, escrow_id, auditor_secret, request_id) -> TxResult:
    auditor = Keypair.from_secret(auditor_secret).public_key
    return invoke(cfg, escrow_id, "post_bond", [
        scval.to_address(Address(auditor)),
        scval.to_uint32(int(request_id)),
    ], auditor_secret)


def settle(cfg, escrow_id, admin_secret, request_id) -> TxResult:
    """Signed by the escrow admin. Pays fee+bond to the bonded auditor."""
    return invoke(cfg, escrow_id, "settle", [scval.to_uint32(int(request_id))], admin_secret)


def slash(cfg, escrow_id, admin_secret, request_id, reporter) -> TxResult:
    """Signed by the escrow admin. Forfeits the bond to `reporter`, refunds the fee."""
    return invoke(cfg, escrow_id, "slash", [
        scval.to_uint32(int(request_id)),
        scval.to_address(Address(reporter)),
    ], admin_secret)


def query_skill(cfg: PipelineConfig, registry_id: str, skill_id: str) -> dict:
    return simulate(cfg, registry_id, "query_skill", [scval.to_string(skill_id)])


def get_version(cfg: PipelineConfig, registry_id: str, skill_id: str, version: str) -> dict:
    return simulate(cfg, registry_id, "get_version",
                    [scval.to_string(skill_id), scval.to_string(version)])
