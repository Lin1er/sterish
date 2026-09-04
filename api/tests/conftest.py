import os

# Point every test at a throwaway DB and a known contract id before the app imports
# its settings (config.py reads the environment once, at import time).
os.environ.setdefault("REGISTRY_CONTRACT_ID", "CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND")
os.environ.setdefault("STELLAR_NETWORK_PASSPHRASE", "Test SDF Network ; September 2015")
os.environ.setdefault("INDEXER_ENABLED", "0")

import tempfile  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    """Each test gets its own SQLite file, so nothing leaks between tests.

    `Settings` is a frozen dataclass and every module imported the instance by value,
    so the one shared object is mutated in place via `object.__setattr__` and restored
    afterwards — patching `config.settings` itself would not reach those modules.
    """
    from sterish_api import config, indexer

    db = tmp_path / "index.db"
    previous = config.settings.db_path
    object.__setattr__(config.settings, "db_path", str(db))
    indexer.init_db()
    try:
        yield db
    finally:
        object.__setattr__(config.settings, "db_path", previous)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from sterish_api.main import app

    with TestClient(app) as c:
        yield c


SAFE_RECORD = {
    "skill_id": "com.acme.pdf-suite",
    "version": "1.0.0",
    "content_hash": "a" * 64,
    "verdict": "SAFE",
    "trust_score": 88,
    "is_verified": True,
    "owner": "GBRPX4" + "A" * 50,
    "auditor": "GCBYQK" + "A" * 50,
    "registered_at": 1756800000,
    "audited_at": 1756810000,
    "evidence_hash": "b" * 64,
}
