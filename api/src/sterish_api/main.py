"""Sterish Verification API.

Serves audit verdicts read live from the SkillRegistry contract on Soroban.
Contract: docs/api-spec.md v1.0.0 (frozen at STE-10).
"""

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import chain, indexer
from .chain import ChainError, ContractError, NotConfiguredError
from .config import settings
from .errors import (
    ApiError,
    api_error_handler,
    chain_error_handler,
    contract_error_handler,
    not_configured_handler,
)
from .models import HealthResponse
from .ratelimit import RateLimitMiddleware
from .routes.check import router as check_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_VERSION = "1.0.0"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.registry_contract_id:
        # Fail loudly (api-spec section 6). The scaffold silently served mock data here,
        # which is how a "SAFE" answer could be produced with no chain behind it at all.
        logger.error(
            "REGISTRY_CONTRACT_ID (or REGISTRY_CA) is not set — every read will return 503"
        )
    else:
        logger.info(
            "registry=%s network=%s rpc=%s",
            settings.registry_contract_id, settings.network, settings.rpc_url,
        )

    # Create the schema either way: with polling off the tables stay empty, but /feed
    # and the evidence lookups then read an empty index instead of erroring on a
    # missing table.
    indexer.init_db()

    task = None
    if settings.indexer_enabled:
        task = asyncio.create_task(indexer.run_forever())
    else:
        logger.info("indexer disabled; evidence tx links will be served as null")

    yield

    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Sterish Verification API",
    description="On-chain audit verification for AI agent skills on Stellar",
    version=API_VERSION,
    lifespan=lifespan,
)

# Everything served is public ledger data, so CORS is open by design (api-spec 6).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(ContractError, contract_error_handler)
app.add_exception_handler(ChainError, chain_error_handler)
app.add_exception_handler(NotConfiguredError, not_configured_handler)

app.include_router(check_router, prefix="", tags=["verification"])


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """503 when the chain cannot be read: a health check that reports ok while the API
    cannot answer a single question is worse than no health check (api-spec 3.5)."""
    reachable, latest = await asyncio.to_thread(chain.rpc_reachable)

    lag = None
    indexed = indexer.last_indexed_ledger() if settings.indexer_enabled else None
    if reachable and latest is not None and indexed is not None:
        lag = max(0, latest - indexed)

    body = HealthResponse(
        status="ok" if reachable else "degraded",
        version=API_VERSION,
        network=settings.network,
        registry_contract_id=settings.registry_contract_id,
        rpc_url=settings.rpc_url,
        rpc_reachable=reachable,
        indexer_lag_ledgers=lag,
    )
    return JSONResponse(status_code=200 if reachable else 503, content=body.model_dump())
