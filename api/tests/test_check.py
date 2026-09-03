import pytest
from fastapi.testclient import TestClient


class TestCheckEndpoint:
    def test_safe_skill(self, client: TestClient) -> None:
        resp = client.get("/check/com.example.web-search")
        assert resp.status_code == 200
        body = resp.json()
        assert body["skill_id"] == "com.example.web-search"
        assert body["verdict"] == "SAFE"
        assert body["trust_score"] == 92
        assert len(body["evidence_hash"]) == 64
        assert body["versions"][0]["version"] == "1.0.0"

    def test_dangerous_skill(self, client: TestClient) -> None:
        body = client.get("/check/com.evil.token-drainer").json()
        assert body["verdict"] == "DANGEROUS"
        assert body["trust_score"] < 40

    def test_warning_skill(self, client: TestClient) -> None:
        body = client.get("/check/com.example.file-manager").json()
        assert body["verdict"] == "WARNING"

    def test_unknown_skill_is_404(self, client: TestClient) -> None:
        resp = client.get("/check/no.such.skill")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    @pytest.mark.parametrize(
        "skill_id",
        ["a b", "../etc/passwd", "%00", "x" * 300],
    )
    def test_hostile_skill_ids_are_404_not_500(self, client: TestClient, skill_id: str) -> None:
        resp = client.get(f"/check/{skill_id}")
        assert resp.status_code in (404, 422), resp.text

    def test_audit_timestamp_is_an_integer(self, client: TestClient) -> None:
        body = client.get("/check/com.example.web-search").json()
        assert isinstance(body["audit_timestamp"], int)
        assert body["audit_timestamp"] > 0


class TestSkillsEndpoint:
    def test_lists_every_fixture_skill(self, client: TestClient) -> None:
        resp = client.get("/skills")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_pagination_slices(self, client: TestClient) -> None:
        first = client.get("/skills?start=0&limit=2").json()
        assert len(first) == 2
        second = client.get("/skills?start=2&limit=2").json()
        assert len(second) == 1
        assert {s["skill_id"] for s in first}.isdisjoint({s["skill_id"] for s in second})

    def test_start_past_the_end_is_empty(self, client: TestClient) -> None:
        assert client.get("/skills?start=99&limit=10").json() == []

    @pytest.mark.parametrize(
        "query",
        ["start=-1", "limit=0", "limit=101", "limit=abc", "start=abc"],
    )
    def test_invalid_pagination_is_422(self, client: TestClient, query: str) -> None:
        assert client.get(f"/skills?{query}").status_code == 422

    def test_rows_carry_version_counts(self, client: TestClient) -> None:
        for row in client.get("/skills").json():
            assert row["versions"] >= 1
            assert 0 <= row["trust_score"] <= 100


class TestFixtureModeGuard:
    def test_configured_contract_disables_fixtures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from sterish_api import client as registry_client

        monkeypatch.setenv("REGISTRY_CONTRACT_ID", "C" + "A" * 55)
        assert registry_client.fixture_mode() is False
        with pytest.raises(NotImplementedError):
            registry_client.query_skill("com.example.web-search")
