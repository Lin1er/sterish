from fastapi.testclient import TestClient


class TestHealth:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"

    def test_health_carries_a_timestamp(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert body["timestamp"]
        # ISO-8601 with timezone, parseable by the stdlib.
        from datetime import datetime

        assert datetime.fromisoformat(body["timestamp"]).tzinfo is not None

    def test_health_reports_the_configured_network(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert body["network"] == "Test SDF Network ; September 2015"

    def test_openapi_schema_builds(self, client: TestClient) -> None:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        paths = resp.json()["paths"]
        assert "/health" in paths
        assert "/skills" in paths
        assert "/check/{skill_id}" in paths


class TestCors:
    def test_preflight_is_allowed(self, client: TestClient) -> None:
        resp = client.options(
            "/skills",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"
