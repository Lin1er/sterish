"""Demo buyer endpoints (STE-43, api-spec 3.10).

`POST /demo/purchases` starts a purchase and returns a job at once; the dashboard polls
`GET /demo/purchases/{job_id}` and draws each step as it completes. See demo_buyer.py
for why this goes through the public `/use` rather than around it.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import demo_buyer

router = APIRouter()

# Sync `def`: start() reads the chain and the artifact before it returns.


class PurchaseRequest(BaseModel):
    skill_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)


def client_id(request: Request) -> str:
    """Who is asking, for the per-client limit.

    Behind Cloudflare and Caddy every request arrives from the proxy, so the proxy's
    forwarding headers are consulted first. They can be forged by a direct caller;
    that only weakens this one limit, which is why the single-flight lock and the
    daily cap exist regardless of who the caller claims to be.
    """
    forwarded = request.headers.get("CF-Connecting-IP") or (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    )
    return forwarded or (request.client.host if request.client else "unknown")


@router.get("/demo/status")
def demo_status():
    return demo_buyer.buyer.status()


@router.post("/demo/purchases", status_code=202)
def start_purchase(body: PurchaseRequest, request: Request):
    job = demo_buyer.buyer.start(body.skill_id.strip(), body.version.strip(), client_id(request))
    return JSONResponse(
        status_code=202,
        content=job.to_dict(),
        headers={"Location": f"/demo/purchases/{job.job_id}", "Cache-Control": "no-store"},
    )


@router.get("/demo/purchases/{job_id}")
def get_purchase(job_id: str):
    return JSONResponse(
        content=demo_buyer.buyer.get(job_id).to_dict(), headers={"Cache-Control": "no-store"}
    )
