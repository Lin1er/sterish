"""The paid path: `GET /use/{skill_id}/{version}` (api-spec 3.7, STE-19).

Three outcomes, in the order they are checked:

1. the caller already holds a license for this exact version -> 200, no payment;
2. no license and no payment -> 402 with x402 requirements;
3. no license, payment attached -> facilitator verify, then settle, then mint the
   license, then 200.

Verify runs before settle deliberately: settling first would move money for a
request that is about to be refused.

What is served is content-pinned. The bytes are hashed and compared with the
`content_hash` the registry holds for that version before they leave this
process, so a buyer cannot pay for one artifact and receive another. A mismatch
is a 500, never a 200 with the wrong bytes.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Request, Response

from .. import chain, x402
from ..config import settings
from ..errors import ApiError

logger = logging.getLogger(__name__)

router = APIRouter()

AGENT_HEADER = "X-AGENT-ADDRESS"


def _agent_address(request: Request) -> str | None:
    """Who is asking. Needed before any payment exists, to answer 'do you already
    hold a licence?'. After payment the address is taken from the payment itself."""
    value = request.headers.get(AGENT_HEADER) or request.query_params.get("agent")
    return value.strip() if value else None


def _skill_bytes(skill_id: str, version: str, expected_hash: str) -> bytes:
    """Read the pinned artifact and refuse to serve anything that is not it."""
    if not settings.skills_dir:
        raise ApiError(503, "NOT_CONFIGURED", "STERISH_SKILLS_DIR is not set")

    root = Path(settings.skills_dir) / skill_id / version
    if not root.is_dir():
        raise ApiError(
            404, "ARTIFACT_NOT_FOUND",
            f"no artifact on disk for {skill_id}@{version}",
        )

    from sterish_pipeline.content_hash import content_hash, read_skill_files

    files = read_skill_files(root)
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

    import json

    return json.dumps(
        {name: raw.decode("utf-8", "replace") for name, raw in sorted(files.items())},
        indent=2,
    ).encode("utf-8")


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


@router.get("/use/{skill_id}/{version}")
async def use_skill(skill_id: str, version: str, request: Request):
    record = chain.get_version(skill_id, version)

    # A licence is only sellable for a version the registry called SAFE. The tokens
    # contract enforces this too (mint_license is gated on the VERIFIED badge), so
    # this is defence in depth and a clearer error than a contract revert.
    if not record["is_verified"]:
        raise ApiError(
            403, "NOT_VERIFIED",
            f"{skill_id}@{version} is {record['verdict']}; only SAFE versions are licensable",
        )

    agent = _agent_address(request)
    payment_header = request.headers.get(x402.PAYMENT_HEADER)

    # 1. Already licensed -> serve, no payment.
    if agent and not payment_header:
        try:
            if chain.has_license(agent, skill_id, version):
                return Response(
                    content=_skill_bytes(skill_id, version, record["content_hash"]),
                    media_type="application/json",
                    headers={"X-STERISH-LICENSE": "held"},
                )
        except chain.ContractError:
            pass  # no licence recorded; fall through to the 402

    resource_url = str(request.url)
    requirements = x402.payment_requirements(
        resource_url, f"License for {skill_id}@{version}"
    )

    # 2. No payment attached -> challenge.
    if not payment_header:
        return Response(
            content=b"{}",
            status_code=402,
            media_type="application/json",
            headers={
                x402.PAYMENT_REQUIRED_HEADER: x402.encode_header(requirements),
                "Cache-Control": "no-store",
            },
        )

    # 3. Payment attached -> verify, settle, mint, serve.
    try:
        payment = x402.decode_header(payment_header)
    except ValueError as exc:
        raise ApiError(400, "INVALID_PAYMENT", str(exc)) from exc

    accepts = requirements["accepts"][0]
    try:
        x402.verify(payment, accepts)
        receipt = x402.settle(payment, accepts)
    except x402.PaymentInvalid as exc:
        raise ApiError(402, "PAYMENT_REJECTED", exc.reason) from exc
    except x402.FacilitatorError as exc:
        # The facilitator is a third party. Its absence must not read as "you did
        # not pay" — that would invite a buyer to pay twice.
        raise ApiError(503, "FACILITATOR_UNAVAILABLE", str(exc)) from exc

    payer = (
        payment.get("payload", {}).get("payer")
        or payment.get("payer")
        or agent
    )
    if not payer:
        raise ApiError(
            400, "UNKNOWN_PAYER",
            f"cannot tell who paid; send {AGENT_HEADER} with the request",
        )

    mint_tx = _mint_license(payer, skill_id, version)

    return Response(
        content=_skill_bytes(skill_id, version, record["content_hash"]),
        media_type="application/json",
        headers={
            x402.PAYMENT_RESPONSE_HEADER: x402.encode_header(receipt),
            "X-STERISH-LICENSE": "minted",
            "X-STERISH-LICENSE-TX": mint_tx,
        },
    )
