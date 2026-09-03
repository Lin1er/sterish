"""Submit audit verdicts to, and read them back from, the deployed contracts.

Rewritten from the scaffold, which had two defects that would have failed
against a live contract:

1. The verdict was encoded as ``scval.to_uint32(2)``. The registry's
   ``submit_verdict`` takes an ``AuditVerdict`` — a Soroban unit-variant enum,
   which encodes as ``ScVal::Vec([ScVal::Symbol("Safe")])``, not a u32. A u32
   argument is a type mismatch the host rejects before the function runs.
2. It drove ``Server`` / ``prepare_transaction`` by hand. stellar-sdk's
   ``ContractClient`` is the supported path: it simulates, assembles, signs, and
   submits, and parses the result ScVal.

Argument encoding is separated from transport (``encode_*`` functions return
``SCVal`` lists) so the encoding — the part that must match the contract ABI
byte-for-byte — is unit-testable with no network. Transport goes through the
``ChainClient`` protocol, which the live client implements and tests fake.

Contract ABI this module targets (the FROZEN interfaces, docs/specs/interfaces.md,
matching contracts/registry and contracts/escrow on main):

    registry.register_skill(owner: Address, skill_id: String, version: String,
                            content_hash: BytesN<32>) -> Result<(), RegistryError>
    registry.submit_verdict(skill_id: String, version: String, verdict: AuditVerdict,
                            score: u32, evidence_hash: BytesN<32>) -> Result<(), RegistryError>
    registry.query_skill(skill_id: String) -> Result<SkillEntry, RegistryError>
    escrow.settle(request_id: u32)
    escrow.slash(request_id: u32)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from stellar_sdk import Keypair, scval
from stellar_sdk.xdr import SCVal

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import FinalVerdict

logger = logging.getLogger(__name__)

# FinalVerdict -> the registry's AuditVerdict variant name. These strings are
# the contract's enum variants; they must match contracts/registry/src/data.rs.
VERDICT_TO_VARIANT: dict[FinalVerdict, str] = {
    FinalVerdict.SAFE: "Safe",
    FinalVerdict.DANGEROUS: "Dangerous",
    FinalVerdict.WARNING: "Warning",
}
VARIANT_TO_VERDICT: dict[str, FinalVerdict] = {v: k for k, v in VERDICT_TO_VARIANT.items()}
UNAUDITED_VARIANT = "Unaudited"


class OnChainError(RuntimeError):
    """A contract interaction failed."""


def _bytes32(evidence_hash: str) -> bytes:
    raw = bytes.fromhex(evidence_hash)
    if len(raw) != 32:
        raise OnChainError(f"evidence_hash must be 32 bytes (64 hex chars), got {len(raw)} bytes")
    return raw


# --- Argument encoding (network-free, ABI-critical) --------------------------


def encode_verdict(verdict: FinalVerdict) -> SCVal:
    """Encode a verdict as the registry's ``AuditVerdict`` enum.

    This is the fix for the scaffold's bug: a Soroban unit-variant enum is a
    Vec-with-a-Symbol, never a plain integer.
    """
    variant = VERDICT_TO_VARIANT.get(verdict)
    if variant is None:
        raise OnChainError(f"no on-chain variant for verdict {verdict!r}")
    return scval.to_enum(variant, None)


def encode_register_skill_args(
    owner: str, skill_id: str, version: str, content_hash: str
) -> list[SCVal]:
    """Args for register_skill(owner, skill_id, version, content_hash)."""
    return [
        scval.to_address(owner),
        scval.to_string(skill_id),
        scval.to_string(version),
        scval.to_bytes(_bytes32(content_hash)),
    ]


def encode_submit_verdict_args(
    skill_id: str, version: str, verdict: FinalVerdict, score: int, evidence_hash: str
) -> list[SCVal]:
    """Args for submit_verdict(skill_id, version, verdict, score, evidence_hash)."""
    if not 0 <= score <= 100:
        raise OnChainError(f"score must be in 0..=100, got {score}")
    return [
        scval.to_string(skill_id),
        scval.to_string(version),
        encode_verdict(verdict),
        scval.to_uint32(score),
        scval.to_bytes(_bytes32(evidence_hash)),
    ]


def encode_query_skill_args(skill_id: str) -> list[SCVal]:
    return [scval.to_string(skill_id)]


def encode_request_id_args(request_id: int) -> list[SCVal]:
    if request_id < 0:
        raise OnChainError(f"request_id must be non-negative, got {request_id}")
    return [scval.to_uint32(request_id)]


# --- Transport ---------------------------------------------------------------


class ChainClient(Protocol):
    """Minimal contract-call surface. The live client and tests both satisfy it."""

    def invoke(
        self, contract_id: str, function: str, args: Sequence[SCVal], signer: Keypair
    ) -> str:
        """Sign, submit, and confirm a state-changing call. Returns the tx hash."""

    def read(self, contract_id: str, function: str, args: Sequence[SCVal]) -> SCVal | None:
        """Simulate a read-only call and return the result ScVal (or None)."""


class SorobanChainClient:
    """`ChainClient` backed by a live Soroban RPC via stellar-sdk.

    Constructed lazily so importing this module never requires a network or a
    configured contract — the orchestrator and its tests import it freely.
    """

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.cfg = config or PipelineConfig()

    def _client(self, contract_id: str):
        from stellar_sdk.contract import ContractClient

        return ContractClient(
            contract_id=contract_id,
            rpc_url=self.cfg.rpc_url,
            network_passphrase=self.cfg.network_passphrase,
        )

    def invoke(
        self, contract_id: str, function: str, args: Sequence[SCVal], signer: Keypair
    ) -> str:
        assembled = self._client(contract_id).invoke(
            function_name=function,
            parameters=list(args),
            source=signer.public_key,
            signer=signer,
        )
        result = assembled.sign_and_submit(signer)
        # sign_and_submit returns the parsed result; the tx hash is on the
        # assembled transaction's sent record.
        tx_hash = getattr(getattr(assembled, "sent_transaction", None), "hash", None)
        if tx_hash:
            return tx_hash
        # Fall back to whatever the SDK surfaced.
        return str(result)

    def read(self, contract_id: str, function: str, args: Sequence[SCVal]) -> SCVal | None:
        assembled = self._client(contract_id).invoke(
            function_name=function,
            parameters=list(args),
            simulate=True,
        )
        return assembled.result()


# --- Orchestration -----------------------------------------------------------


@dataclass
class SubmissionResult:
    """The outcome of pushing one skill's audit on-chain."""

    skill_id: str
    verdict: FinalVerdict
    registered: bool = False
    register_tx: str = ""
    verdict_tx: str = ""
    settle_tx: str = ""
    slash_tx: str = ""
    evidence_hash: str = ""
    report_uri: str = ""
    steps: list[str] = field(default_factory=list)

    def _note(self, step: str) -> None:
        self.steps.append(step)
        logger.info("%s: %s", self.skill_id, step)


@dataclass
class RetryPolicy:
    attempts: int = 3
    backoff_seconds: float = 2.0


class VerdictOrchestrator:
    """Drive one skill's audit result through the deployed contracts.

    The full path per skill:

        (register_skill if not already recorded)
        -> submit_verdict
        -> SAFE:      settle the escrow request (auditor paid)
           DANGEROUS: optionally slash (bond forfeited)

    Steps are ordered so a mid-run RPC failure leaves resumable state: the
    idempotent register check means a re-run skips work already on-chain.
    """

    def __init__(
        self,
        client: ChainClient,
        registry_contract_id: str,
        escrow_contract_id: str = "",
        auditor: Keypair | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        if not registry_contract_id:
            raise OnChainError("registry_contract_id is required")
        self.client = client
        self.registry_id = registry_contract_id
        self.escrow_id = escrow_contract_id
        self.auditor = auditor
        self.retry = retry or RetryPolicy()

    # -- individual operations --

    def is_registered(self, skill_id: str) -> bool:
        try:
            result = self.client.read(
                self.registry_id, "query_skill", encode_query_skill_args(skill_id)
            )
        except Exception as exc:  # noqa: BLE001 - a read failure means "unknown"
            logger.debug("query_skill(%s) failed, treating as unregistered: %s", skill_id, exc)
            return False
        return result is not None

    def _owner(self, owner: str | None) -> str:
        # register_skill does owner.require_auth(), so the owner must be the
        # signer. Default it to the auditor's own account.
        if owner:
            return owner
        if self.auditor is None:
            raise OnChainError("an owner address (or an auditor keypair) is required")
        return self.auditor.public_key

    def register_skill(
        self, skill_id: str, version: str, content_hash: str, owner: str | None = None
    ) -> str:
        return self._invoke(
            "register_skill",
            self.registry_id,
            encode_register_skill_args(self._owner(owner), skill_id, version, content_hash),
        )

    def submit_verdict(
        self, skill_id: str, version: str, verdict: FinalVerdict, score: int, evidence_hash: str
    ) -> str:
        return self._invoke(
            "submit_verdict",
            self.registry_id,
            encode_submit_verdict_args(skill_id, version, verdict, score, evidence_hash),
        )

    def settle(self, request_id: int) -> str:
        if not self.escrow_id:
            raise OnChainError("escrow_contract_id not configured; cannot settle")
        return self._invoke("settle", self.escrow_id, encode_request_id_args(request_id))

    def slash(self, request_id: int) -> str:
        if not self.escrow_id:
            raise OnChainError("escrow_contract_id not configured; cannot slash")
        return self._invoke("slash", self.escrow_id, encode_request_id_args(request_id))

    # -- full flow --

    def submit_audit(
        self,
        skill_id: str,
        version: str,
        verdict: FinalVerdict,
        score: int,
        evidence_hash: str,
        content_hash: str,
        owner: str | None = None,
        request_id: int | None = None,
        report_uri: str = "",
        slash_on_dangerous: bool = False,
    ) -> SubmissionResult:
        """Push one skill's audit through the full contract flow."""
        result = SubmissionResult(
            skill_id=skill_id,
            verdict=verdict,
            evidence_hash=evidence_hash,
            report_uri=report_uri,
        )

        if self.is_registered(skill_id):
            result._note("already registered; skipping register_skill")
        else:
            result.register_tx = self.register_skill(skill_id, version, content_hash, owner)
            result.registered = True
            result._note(f"register_skill tx={result.register_tx}")

        result.verdict_tx = self.submit_verdict(skill_id, version, verdict, score, evidence_hash)
        result._note(f"submit_verdict({verdict.value}) tx={result.verdict_tx}")

        if request_id is not None:
            if verdict == FinalVerdict.SAFE:
                result.settle_tx = self.settle(request_id)
                result._note(f"settle(request {request_id}) tx={result.settle_tx}")
            elif verdict == FinalVerdict.DANGEROUS and slash_on_dangerous:
                result.slash_tx = self.slash(request_id)
                result._note(f"slash(request {request_id}) tx={result.slash_tx}")
            else:
                result._note(f"verdict {verdict.value}: escrow left untouched (no settle/slash)")

        return result

    # -- internals --

    def _invoke(self, function: str, contract_id: str, args: Sequence[SCVal]) -> str:
        if self.auditor is None:
            raise OnChainError(f"an auditor keypair is required to call {function}")
        last_exc: Exception | None = None
        for attempt in range(1, self.retry.attempts + 1):
            try:
                return self.client.invoke(contract_id, function, args, self.auditor)
            except Exception as exc:  # noqa: BLE001 - ret/re-raise below
                last_exc = exc
                logger.warning(
                    "%s attempt %d/%d failed: %s", function, attempt, self.retry.attempts, exc
                )
                if attempt < self.retry.attempts:
                    time.sleep(self.retry.backoff_seconds * attempt)
        raise OnChainError(f"{function} failed after {self.retry.attempts} attempts: {last_exc}")


# --- Backwards-compatible helpers --------------------------------------------
#
# The CLI's `audit --submit` path calls submit_verdict_to_chain(...). Keep the
# name, but route it through the corrected encoding and transport.


def submit_verdict_to_chain(
    contract_id: str,
    skill_id: str,
    version: str,
    verdict: FinalVerdict,
    score: int,
    evidence_hash: str,
    secret_key: str,
    public_key: str = "",
    config: PipelineConfig | None = None,
    client: ChainClient | None = None,
) -> str:
    """Submit a single verdict for (skill_id, version). Returns the tx hash."""
    kp = Keypair.from_secret(secret_key)
    if public_key and kp.public_key != public_key:
        raise OnChainError("secret key does not match the provided public key")

    chain = client or SorobanChainClient(config)
    orchestrator = VerdictOrchestrator(
        client=chain,
        registry_contract_id=contract_id,
        auditor=kp,
    )
    return orchestrator.submit_verdict(skill_id, version, verdict, score, evidence_hash)


def query_skill_from_chain(
    contract_id: str,
    skill_id: str,
    config: PipelineConfig | None = None,
    client: ChainClient | None = None,
) -> SCVal | None:
    """Read a skill entry from the registry. Returns the raw result ScVal."""
    chain = client or SorobanChainClient(config)
    return chain.read(contract_id, "query_skill", encode_query_skill_args(skill_id))
