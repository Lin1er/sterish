"""One error shape for every failure: {"error": CODE, "detail": "..."}.

api-spec section 4. The rule that matters: a read failure is never a 200 with a
default verdict. If the chain cannot be read the API says 502, because serving an
invented "SAFE" is the worst thing this service could do.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from .chain import ChainError, ContractError, NotConfiguredError
from .config import (
    REGISTRY_ERR_NOT_INITIALIZED,
    REGISTRY_ERR_SKILL_NOT_FOUND,
    REGISTRY_ERR_VERSION_NOT_FOUND,
)


class ApiError(Exception):
    def __init__(
        self, status: int, error: str, detail: str = "", extra: dict | None = None
    ):
        super().__init__(detail or error)
        self.status = status
        self.error = error
        self.detail = detail
        self.extra = extra or {}


def error_body(error: str, detail: str, extra: dict | None = None) -> dict:
    body = {"error": error, "detail": detail}
    body.update(extra or {})
    return body


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status, content=error_body(exc.error, exc.detail, exc.extra)
    )


async def contract_error_handler(request: Request, exc: ContractError) -> JSONResponse:
    """Map the frozen ABI error numbers onto the spec's HTTP errors.

    The 404 detail names the skill/version that missed, so a caller can tell
    "no such skill" from "that skill has no such version" without a second request.
    """
    params = request.path_params
    skill_id = params.get("skill_id", "")
    version = params.get("version", "")

    if exc.code == REGISTRY_ERR_SKILL_NOT_FOUND:
        return JSONResponse(
            status_code=404,
            content=error_body("SKILL_NOT_FOUND", f"skill {skill_id!r} is not registered"),
        )
    if exc.code == REGISTRY_ERR_VERSION_NOT_FOUND:
        return JSONResponse(
            status_code=404,
            content=error_body(
                "VERSION_NOT_FOUND", f"skill {skill_id!r} has no version {version!r}"
            ),
        )
    if exc.code == REGISTRY_ERR_NOT_INITIALIZED:
        return JSONResponse(
            status_code=503,
            content=error_body("NOT_CONFIGURED", "registry contract is not initialized"),
        )
    return JSONResponse(
        status_code=500, content=error_body("INTERNAL", f"contract error #{exc.code}")
    )


async def chain_error_handler(_: Request, exc: ChainError) -> JSONResponse:
    return JSONResponse(status_code=502, content=error_body("RPC_UNAVAILABLE", str(exc)))


async def not_configured_handler(_: Request, exc: NotConfiguredError) -> JSONResponse:
    return JSONResponse(status_code=503, content=error_body("NOT_CONFIGURED", str(exc)))
