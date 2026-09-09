"""`GET /license/{skill_id}/{version}` — does this agent hold a licence? (STE-35)

Before this endpoint the only way to ask was `GET /use/...` with an agent header,
which answers by **serving the whole artifact** on success. Drawing one badge cost a
full skill download; a detail page with five versions cost five.

Worse, it did not actually answer the question. Three ways `/use` gets it wrong:

1. It reads the artifact from disk before replying, so an agent that genuinely holds
   a licence still gets `404 ARTIFACT_NOT_FOUND` for any skill not published to
   `STERISH_SKILLS_DIR` — 46 of the 47 skills in the live registry, at the time of
   writing. "No licence" and "no artifact on disk" were indistinguishable.
2. It swallows a chain read failure and falls through to the 402 challenge, so 402
   meant either "you have no licence" or "we could not tell".
3. It refuses non-SAFE versions with 403 before it ever looks at the licence, so a
   version re-audited to DANGEROUS hides its existing licence holders — precisely
   the case a dashboard most needs to show.

So this endpoint answers the licence question and nothing else: it never touches the
registry verdict, never touches the artifact directory, and reports a failed read as
a failed read.
"""

from fastapi import APIRouter, Query, Request
from stellar_sdk.strkey import StrKey

from .. import chain
from ..config import settings
from ..errors import ApiError
from ..models import LicenseStatusResponse

router = APIRouter()

# Sync `def`, not `async def`: the Soroban simulation inside is blocking IO. See the
# note in routes/use.py — declared async it would run on the event loop.

AGENT_HEADER = "X-AGENT-ADDRESS"


def _agent_address(request: Request, agent: str | None) -> str:
    """The agent to ask about, from `?agent=` or the header, in that order.

    Validated here rather than left to `Address(...)` inside the chain layer: a bad
    address should be a 400 naming the problem, not a 500 from an XDR encoder.
    """
    value = agent or request.headers.get(AGENT_HEADER) or ""
    value = value.strip()

    if not value:
        raise ApiError(
            400,
            "MISSING_AGENT",
            f"pass the agent account as ?agent=G... or the {AGENT_HEADER} header",
        )
    # Only ed25519 account addresses hold licences. Contract addresses (C...) and
    # muxed accounts (M...) are rejected rather than quietly encoded into a read that
    # would return false for the wrong reason.
    if not StrKey.is_valid_ed25519_public_key(value):
        raise ApiError(
            400,
            "INVALID_AGENT",
            f"agent must be a Stellar account address (G...), got {value!r}",
        )
    return value


@router.get("/license/{skill_id}/{version}", response_model=LicenseStatusResponse)
def license_status(
    skill_id: str,
    version: str,
    request: Request,
    agent: str | None = Query(default=None, description="Stellar account address (G...)"),
):
    """Read-only mirror of `has_license` on the tokens contract.

    Deliberately unconditional on the registry verdict and on the artifact directory:
    holding a licence is a fact about the tokens contract alone.

    A licence is pinned to one (skill_id, version) pair, so an unregistered skill and
    a never-licensed one both answer `held: false` — that is the contract's own answer,
    not a guess. A chain read that *fails* raises instead, surfacing as 502
    RPC_UNAVAILABLE, because "we could not tell" must never be served as "no".
    """
    if not skill_id or not version:
        raise ApiError(400, "INVALID_PARAMETER", "skill_id and version must be non-empty")

    agent_address = _agent_address(request, agent)

    if not settings.tokens_contract_id:
        raise ApiError(503, "NOT_CONFIGURED", "TOKENS_CONTRACT_ID (or TOKENS_CA) is not set")

    return LicenseStatusResponse(
        skill_id=skill_id,
        version=version,
        agent=agent_address,
        held=chain.has_license(agent_address, skill_id, version),
        tokens_contract_id=settings.tokens_contract_id,
        contract_url=settings.contract_url(settings.tokens_contract_id),
    )
