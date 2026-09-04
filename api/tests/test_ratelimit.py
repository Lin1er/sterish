from fastapi import FastAPI
from fastapi.testclient import TestClient

from sterish_api.ratelimit import RateLimitMiddleware


def _app(limit):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit_per_minute=limit)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    return TestClient(app)


def test_requests_over_the_limit_get_429():
    c = _app(3)
    assert [c.get("/ping").status_code for _ in range(3)] == [200, 200, 200]
    r = c.get("/ping")
    assert r.status_code == 429
    assert r.json()["error"] == "RATE_LIMITED"
    assert "Retry-After" in r.headers


def test_health_is_exempt_so_probes_never_trip_the_limit():
    c = _app(1)
    c.get("/ping")
    assert all(c.get("/health").status_code == 200 for _ in range(5))


def test_limit_of_zero_disables_the_middleware():
    c = _app(0)
    assert all(c.get("/ping").status_code == 200 for _ in range(10))
