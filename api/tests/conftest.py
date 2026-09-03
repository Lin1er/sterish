import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def fixture_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs against the fixture registry, never a live contract."""
    monkeypatch.delenv("REGISTRY_CONTRACT_ID", raising=False)


@pytest.fixture
def client() -> TestClient:
    from sterish_api.main import app

    return TestClient(app)
