"""x402 v2 seller side: the 402 challenge, and verify/settle through the facilitator.

The x402 middleware that Stellar documents is Node-only (`@x402/express`), but the
facilitator is a plain HTTP service exposing `/verify`, `/settle` and `/supported`.
That is the whole server-side dependency, so the seller lives here in FastAPI
rather than behind a Node sidecar.

The wire format below was captured from the reference `@x402/express` server run
against this same facilitator, not inferred from prose. A 402 carries the
requirements in a `PAYMENT-REQUIRED` header as base64 JSON, with an empty body:

    {"x402Version": 2, "error": "...", "resource": {...},
     "accepts": [{"scheme": "exact", "network": "stellar:testnet",
                  "amount": "1000000", "asset": "<USDC SAC C...>",
                  "payTo": "<G...>", "maxTimeoutSeconds": 300,
                  "extra": {"areFeesSponsored": true}}]}

`amount` is in 7-decimal base units — the reference server rendered "$0.10" as
"1000000". `asset` is the SAC contract; `payTo` is a classic account. Swapping
those two is the documented common stumble, so they come from separate settings
and `payment_requirements` never derives one from the other.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)

X402_VERSION = 2
PAYMENT_REQUIRED_HEADER = "PAYMENT-REQUIRED"
PAYMENT_HEADER = "X-PAYMENT"
PAYMENT_RESPONSE_HEADER = "X-PAYMENT-RESPONSE"

# The facilitator sponsors network fees, which is what lets a buyer hold zero XLM.
# Advertised by /supported as extra.areFeesSponsored.
NETWORK = "stellar:testnet"


class FacilitatorError(Exception):
    """The facilitator was unreachable or answered with something unusable."""


class PaymentInvalid(Exception):
    """The facilitator rejected the payment. `reason` is its own wording."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def payment_requirements(resource_url: str, description: str) -> dict[str, Any]:
    """The body of the PAYMENT-REQUIRED header for one paid resource."""
    return {
        "x402Version": X402_VERSION,
        "error": "Payment required",
        "resource": {
            "url": resource_url,
            "description": description,
            "mimeType": "application/json",
        },
        "accepts": [
            {
                "scheme": "exact",
                "network": NETWORK,
                "amount": str(settings.price_base_units),
                "asset": settings.usdc_sac,
                "payTo": settings.pay_to,
                "maxTimeoutSeconds": 300,
                "extra": {"areFeesSponsored": True},
            }
        ],
    }


def encode_header(payload: dict[str, Any]) -> str:
    """base64 of the compact JSON, matching what the reference server emits."""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def decode_header(value: str) -> dict[str, Any]:
    """Decode an X-PAYMENT header. Raises ValueError on anything malformed."""
    try:
        return json.loads(base64.b64decode(value, validate=True))
    except Exception as exc:  # base64, utf-8 or json — all mean the same to a caller
        raise ValueError(f"X-PAYMENT is not base64 JSON: {exc}") from exc


def _auth_headers() -> dict[str, str]:
    if not settings.facilitator_api_key:
        raise FacilitatorError(
            "OZ_API_KEY is not set; generate one with "
            "`curl https://channels.openzeppelin.com/testnet/gen` (testnet needs no auth)"
        )
    return {"Authorization": f"Bearer {settings.facilitator_api_key}"}


def _post(path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    url = f"{settings.facilitator_url}{path}"
    try:
        response = httpx.post(url, json=body, headers=_auth_headers(), timeout=timeout)
    except httpx.HTTPError as exc:
        raise FacilitatorError(f"facilitator {path} unreachable: {exc}") from exc

    if response.status_code >= 500:
        raise FacilitatorError(f"facilitator {path} returned {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise FacilitatorError(f"facilitator {path} returned non-JSON") from exc


def verify(payment: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    """Ask the facilitator whether this payment satisfies these requirements.

    Verification is cheap and settles nothing, so it runs first: settling an
    invalid payment would move money for a request we are about to refuse.
    """
    result = _post("/verify", {"x402Version": X402_VERSION,
                               "paymentPayload": payment,
                               "paymentRequirements": requirements}, timeout=20.0)
    if not result.get("isValid"):
        raise PaymentInvalid(str(result.get("invalidReason") or "payment rejected"))
    return result


def settle(payment: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    """Settle on chain. Returns the facilitator's receipt, including the tx hash."""
    result = _post("/settle", {"x402Version": X402_VERSION,
                               "paymentPayload": payment,
                               "paymentRequirements": requirements}, timeout=60.0)
    if not result.get("success"):
        raise PaymentInvalid(str(result.get("errorReason") or "settlement failed"))
    return result


def supported() -> dict[str, Any]:
    """`/supported`. Used by /health to report whether the paid path can work."""
    url = f"{settings.facilitator_url}/supported"
    try:
        response = httpx.get(url, headers=_auth_headers(), timeout=10.0)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise FacilitatorError(f"facilitator /supported failed: {exc}") from exc
