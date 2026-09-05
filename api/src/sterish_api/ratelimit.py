"""Fixed-window per-IP rate limit (api-spec section 6: 100 req/min, configurable).

In-process and per-worker on purpose: this is a public read-only API in front of a
public ledger, so the limit exists to blunt accidental hammering, not to enforce a
quota. A shared store would be the right answer behind multiple workers (STE-25).
"""

import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import settings

_EXEMPT = {"/health"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_minute: int | None = None):
        super().__init__(app)
        self.limit = limit_per_minute if limit_per_minute is not None else settings.rate_limit_per_minute
        self._hits: dict[tuple[str, int], int] = defaultdict(int)
        self._lock = Lock()

    async def dispatch(self, request, call_next):
        if self.limit <= 0 or request.url.path in _EXEMPT:
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = (client, window)

        with self._lock:
            # Drop windows that have rolled over so the dict cannot grow without bound.
            for stale in [k for k in self._hits if k[1] != window]:
                del self._hits[stale]
            self._hits[key] += 1
            count = self._hits[key]

        if count > self.limit:
            return JSONResponse(
                status_code=429,
                content={"error": "RATE_LIMITED", "detail": f"more than {self.limit} requests per minute"},
                headers={"Retry-After": str(60 - int(time.time() % 60))},
            )
        return await call_next(request)
