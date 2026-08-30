import asyncio
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.check import router as check_router
from .models import HealthResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sterish Verification API",
    description="On-chain audit verification for AI agent skills on Stellar",
    version="0.1.0",
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
async def health_check():
    return HealthResponse(status="ok", version="0.1.0")


@app.on_event("startup")
async def startup():
    logger.info("Sterish Verification API starting up")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Sterish Verification API shutting down")
