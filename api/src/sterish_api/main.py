import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .models import HealthResponse
from .routes.check import router as check_router

logging.basicConfig(level=os.getenv("STERISH_LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

API_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Sterish Verification API starting up")
    yield
    logger.info("Sterish Verification API shutting down")


app = FastAPI(
    title="Sterish Verification API",
    description="On-chain audit verification for AI agent skills on Stellar",
    version=API_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(check_router, prefix="", tags=["verification"])


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=API_VERSION,
        timestamp=datetime.now(UTC).isoformat(),
        registry_contract_id=os.getenv("REGISTRY_CONTRACT_ID", ""),
        network=os.getenv("STELLAR_NETWORK_PASSPHRASE", "Test SDF Network ; September 2015"),
    )
