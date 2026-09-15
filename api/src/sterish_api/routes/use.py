"""The paid path: `GET /use/{skill_id}/{version}` (api-spec 3.7, STE-19, STE-42).

The rule everything below serves: **never take money for something that cannot be
handed over, and never take it twice.**

Checked in this order:

1. the version is SAFE on chain, else 403 — never offered for sale;
2. the artifact is on disk and hashes to the on-chain `content_hash`, else 404/500 —
   checked *before* the 402, so nothing undeliverable is ever priced;
3. the caller already holds a licence -> 200, no payment;
4. the caller has a settled payment still owed a licence -> finish the mint, 200;
5. no payment attached -> 402 with x402 requirements;
6. payment attached -> verify (which names the payer) -> held or owed? serve without
   settling -> settle -> record the settlement -> mint -> 200.

Before STE-42 the artifact was read only after settle and mint, so every SAFE skill
without a published artifact took 0.10 USDC, minted a licence, and answered 404.

The payer is the account the facilitator's `/verify` names: the `from` of the
signed SAC `transfer`. It is never taken from `X-AGENT-ADDRESS`. That header is only
a hint for the free "already licensed" shortcut, and trusting it after payment let a
licence be minted to whatever address the header carried — or, with no header,
settled the payment and then answered 400 with no licence at all, because the
Stellar exact payload carries no `payer` field of its own.

What is served is content-pinned: the bytes are hashed against the registry's
`content_hash` before they leave this process.
"""

import json
import logging
import threading
from pathlib import Path

from fastapi import APIRouter, Request, Response
from stellar_sdk.strkey import StrKey

from .. import chain, payments, x402
from ..config import settings
from ..errors import ApiError

logger = logging.getLogger(__name__)

router = APIRouter()

# Handlers here are sync `def`, not `async def`, on purpose. Every call they make
# — the Soroban simulations, the facilitator round trips, the licence mint — is
# blocking IO. Declared async they would run ON the event loop and stall every
# other request for their duration; a mint polls the ledger for several seconds,
# so one purchase made the whole API unresponsive. FastAPI runs sync handlers in
# a threadpool, which is exactly what this work wants.

AGENT_HEADER = "X-AGENT-ADDRESS"
SETTLEMENT_TX_HEADER = "X-STERISH-SETTLEMENT-TX"

# tokens contract: TokenError::AlreadyMinted (contracts/tokens/src/data.rs). Frozen.
TOKENS_ERR_ALREADY_MINTED = 3

# One purchase per (payer, skill, version) at a time. Without it two concurrent
# payments from the same account both see "no licence", both settle, and the buyer
# pays twice for one licence. The API runs as a single uvicorn process (Dockerfile
# CMD), so an in-process lock covers every request that can race.
_purchase_locks: dict[tuple[str, str, str], threading.Lock] = {}
_purchase_locks_guard = threading.Lock()


def _purchase_lock(payer: str, skill_id: str, version: str) -> threading.Lock:
    key = (payer, skill_id, version)
    with _purchase_locks_guard:
        lock = _purchase_locks.get(key)
        if lock is None:
            lock = _purchase_locks[key] = threading.Lock()
        return lock


def _agent_hint(request: Request) -> str | None:
    """The caller's claimed account, used only for the free already-licensed shortcut.

    Validated so a malformed value is a 400 naming the problem rather than a 500
    from the XDR encoder. Never used to decide who a paid licence is minted to.
    """
    value = request.headers.get(AGENT_HEADER) or request.query_params.get("agent")
    if not value or not value.strip():
        return None
    value = value.strip()
    if not StrKey.is_valid_ed25519_public_key(value):
        raise ApiError(
            400, "INVALID_AGENT",
            f"agent must be a Stellar account address (G...), got {value!r}",
        )
    return value


def _skill_bytes(skill_id: str, version: str, expected_hash: str) -> bytes:
    """Read the pinned artifact and refuse to serve anything that is not it."""
    if not settings.skills_dir:
        raise ApiError(503, "NOT_CONFIGURED", "STERISH_SKILLS_DIR is not set")

    root = Path(settings.skills_dir) / skill_id / version
    # Resolve and re-check containment: skill_id and version come from the URL, and
    # a `..` segment must not walk the read outside the artifact directory.
    base = Path(settings.skills_dir).resolve()
    if base not in root.resolve().parents or not root.is_dir():
        raise ApiError(
            404, "ARTIFACT_NOT_FOUND",
            f"no artifact on disk for {skill_id}@{version}; it is not offered for sale",
        )

    from sterish_pipeline.content_hash import ContentHashError, content_hash, read_skill_files

    try:
        files = read_skill_files(root)
    except ContentHashError as exc:
        raise ApiError(
            404, "ARTIFACT_NOT_FOUND",
            f"artifact directory for {skill_id}@{version} is unusable: {exc}",
        ) from exc
    actual = content_hash(files)
    if actual != expected_hash:
        # Serving these bytes would break the one promise the licence encodes.
        logger.error(
            "artifact hash mismatch for %s@%s: disk %s, chain %s",
            skill_id, version, actual, expected_hash,
        )
        raise ApiError(
            500, "ARTIFACT_HASH_MISMATCH",
            "artifact on disk does not match the content_hash recorded on chain",
        )

    return json.dumps(
        {name: raw.decode("utf-8", "replace") for name, raw in sorted(files.items())},
        indent=2,
    ).encode("utf-8")


def _has_license(agent: str, skill_id: str, version: str) -> bool:
    """A failed read is a failed read, never "no licence" (which would invite a 402
    and a second payment). A ChainError propagates as 502 through its handler."""
    try:
        return chain.has_license(agent, skill_id, version)
    except chain.ContractError as exc:
        raise ApiError(
            502, "LICENSE_READ_FAILED",
            f"could not read the licence for {agent} from the tokens contract: {exc}",
        ) from exc


def _mint_license(agent: str, skill_id: str, version: str) -> str:
    """Mint the licence with the minter role. Returns the transaction hash."""
    from stellar_sdk import Address, scval
    from sterish_pipeline.config import PipelineConfig
    from sterish_pipeline.onchain import invoke

    if not settings.minter_secret:
        raise ApiError(503, "NOT_CONFIGURED", "MINTER_SECRET is not set")

    cfg = PipelineConfig(
        rpc_url=settings.rpc_url,
        network_passphrase=settings.network_passphrase,
        registry_contract_id=settings.registry_contract_id,
    )
    result = invoke(
        cfg,
        settings.tokens_contract_id,
        "mint_license",
        [
            scval.to_address(Address(agent)),
            scval.to_string(skill_id),
            scval.to_string(version),
        ],
        settings.minter_secret,
    )
    return result.tx_hash


def _fulfil(owed_row: dict, skill_id: str, version: str) -> str | None:
    """Turn a recorded settlement into a licence. Returns the mint tx, or None when
    the licence turned out to be on chain already.

    Checks the chain before minting: a mint whose confirmation timed out may have
    landed, and minting again would only revert with AlreadyMinted.
    """
    from sterish_pipeline.onchain import ContractCallError

    payer, settle_tx = owed_row["payer"], owed_row["settle_tx"]

    if _has_license(payer, skill_id, version):
        payments.mark_minted(settle_tx, None)
        return None

    try:
        mint_tx = _mint_license(payer, skill_id, version)
    except ContractCallError as exc:
        if exc.code == TOKENS_ERR_ALREADY_MINTED:
            payments.mark_minted(settle_tx, None)
            return None
        payments.mark_error(settle_tx, str(exc))
        logger.error("mint_license refused for settled payment %s: %s", settle_tx, exc)
        raise _mint_pending(settle_tx, str(exc)) from exc
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - timeout, RPC, anything: the money moved
        payments.mark_error(settle_tx, str(exc))
        logger.error("mint_license failed for settled payment %s: %s", settle_tx, exc)
        raise _mint_pending(settle_tx, str(exc)) from exc

    payments.mark_minted(settle_tx, mint_tx)
    return mint_tx


def _mint_pending(settle_tx: str, reason: str) -> ApiError:
    return ApiError(
        502, "LICENSE_MINT_PENDING",
        "your payment settled but the licence could not be minted yet; retry the same "
        "request (with X-AGENT-ADDRESS) and it will be finished without charging again. "
        f"Cause: {reason}",
        {
            "settlement_tx": settle_tx,
            "settlement_tx_url": settings.tx_url(settle_tx),
        },
    )


def _serve(body: bytes, licence: str, extra: dict[str, str] | None = None) -> Response:
    headers = {"X-STERISH-LICENSE": licence, "Cache-Control": "no-store"}
    headers.update(extra or {})
    return Response(content=body, media_type="application/json", headers=headers)


def _serve_fulfilled(body: bytes, owed_row: dict, mint_tx: str | None) -> Response:
    headers = {SETTLEMENT_TX_HEADER: owed_row["settle_tx"]}
    if mint_tx:
        headers["X-STERISH-LICENSE-TX"] = mint_tx
    return _serve(body, "minted" if mint_tx else "held", headers)


@router.get("/use/{skill_id}/{version}")
def use_skill(skill_id: str, version: str, request: Request):
    record = chain.get_version(skill_id, version)

    # A licence is only sellable for a version the registry called SAFE. The tokens
    # contract enforces this too (mint_license is gated on the VERIFIED badge), so
    # this is defence in depth and a clearer error than a contract revert.
    if not record["is_verified"]:
        raise ApiError(
            403, "NOT_VERIFIED",
            f"{skill_id}@{version} is {record['verdict']}; only SAFE versions are licensable",
        )

    # Deliverability before price. If these bytes cannot be served, nothing below may
    # run: no challenge, no verify, no settle.
    body = _skill_bytes(skill_id, version, record["content_hash"])

    agent = _agent_hint(request)
    payment_header = request.headers.get(x402.PAYMENT_HEADER)

    if not payment_header:
        if agent:
            if _has_license(agent, skill_id, version):
                # A mint that landed although its confirmation never reached us leaves
                # its settlement looking owed; close it so it is never fulfilled twice.
                stale = payments.owed(agent, skill_id, version)
                if stale:
                    payments.mark_minted(stale["settle_tx"], None)
                return _serve(body, "held")
            owed_row = payments.owed(agent, skill_id, version)
            if owed_row:
                with _purchase_lock(agent, skill_id, version):
                    owed_row = payments.owed(agent, skill_id, version) or owed_row
                    mint_tx = _fulfil(owed_row, skill_id, version)
                return _serve_fulfilled(body, owed_row, mint_tx)

        requirements = x402.payment_requirements(
            str(request.url), f"License for {skill_id}@{version}"
        )
        return Response(
            content=b"{}",
            status_code=402,
            media_type="application/json",
            headers={
                x402.PAYMENT_REQUIRED_HEADER: x402.encode_header(requirements),
                "Cache-Control": "no-store",
            },
        )

    try:
        payment = x402.decode_header(payment_header)
    except ValueError as exc:
        raise ApiError(400, "INVALID_PAYMENT", str(exc)) from exc

    requirements = x402.payment_requirements(
        str(request.url), f"License for {skill_id}@{version}"
    )
    accepts = requirements["accepts"][0]

    try:
        verified = x402.verify(payment, accepts)
    except x402.PaymentInvalid as exc:
        raise ApiError(402, "PAYMENT_REJECTED", exc.reason) from exc
    except x402.FacilitatorError as exc:
        # The facilitator is a third party. Its absence must not read as "you did
        # not pay" — that would invite a buyer to pay twice.
        raise ApiError(503, "FACILITATOR_UNAVAILABLE", str(exc)) from exc

    payer = str(verified.get("payer") or "").strip()
    if not StrKey.is_valid_ed25519_public_key(payer):
        # Settling without knowing who paid would leave nobody to mint the licence
        # to. Refuse while no money has moved.
        raise ApiError(
            502, "FACILITATOR_BAD_RESPONSE",
            f"facilitator verified the payment but named no valid payer ({payer!r})",
        )

    with _purchase_lock(payer, skill_id, version):
        # Re-checked under the lock: a concurrent purchase may have just finished.
        if _has_license(payer, skill_id, version):
            return _serve(body, "held")
        owed_row = payments.owed(payer, skill_id, version)
        if owed_row:
            mint_tx = _fulfil(owed_row, skill_id, version)
            return _serve_fulfilled(body, owed_row, mint_tx)

        try:
            receipt = x402.settle(payment, accepts)
        except x402.PaymentInvalid as exc:
            raise ApiError(402, "PAYMENT_REJECTED", exc.reason) from exc
        except x402.FacilitatorError as exc:
            raise ApiError(503, "FACILITATOR_UNAVAILABLE", str(exc)) from exc

        settle_tx = str(receipt.get("transaction") or "").strip()
        if not settle_tx:
            # success without a transaction hash is not a receipt anyone can check.
            logger.error("facilitator settled with no transaction hash: %s", receipt)
            raise ApiError(
                502, "FACILITATOR_BAD_RESPONSE",
                "facilitator reported success without a settlement transaction",
            )
        if receipt.get("payer") and receipt["payer"] != payer:
            logger.warning(
                "settle named payer %s but verify named %s; minting to the verified payer",
                receipt["payer"], payer,
            )

        try:
            payments.record_settlement(
                payer, skill_id, version, settle_tx, str(accepts["amount"])
            )
        except Exception:  # noqa: BLE001 - the money moved; still try to deliver
            logger.exception(
                "could not record settlement %s for %s; attempting the mint anyway",
                settle_tx, payer,
            )

        owed_row = payments.get(settle_tx) or {"payer": payer, "settle_tx": settle_tx}
        mint_tx = _fulfil(owed_row, skill_id, version)

    headers = {
        x402.PAYMENT_RESPONSE_HEADER: x402.encode_header(receipt),
        SETTLEMENT_TX_HEADER: settle_tx,
    }
    if mint_tx:
        headers["X-STERISH-LICENSE-TX"] = mint_tx
    return _serve(body, "minted", headers)
