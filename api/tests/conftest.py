import os

# Point every test at a throwaway DB and a known contract id before the app imports
# its settings (config.py reads the environment once, at import time).
os.environ.setdefault(
    "REGISTRY_CONTRACT_ID", "CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND"
)
os.environ.setdefault("STELLAR_NETWORK_PASSPHRASE", "Test SDF Network ; September 2015")
os.environ.setdefault("INDEXER_ENABLED", "0")

# x402 settings the paid-path tests assert on. Set here, not inherited: these tests
# passed locally only because a developer shell had .env loaded, and CI — which has
# no .env — caught that the assertions were reading ambient values rather than
# fixed ones.
os.environ.setdefault(
    "TOKENS_CONTRACT_ID", "CCHVZRLOFGZ5IAYQUSHIPQOTVFABOX6SK5MHNZZUKAOT333KZNVW4EJX"
)
os.environ.setdefault(
    "X402_PAY_TO", "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU"
)
os.environ.setdefault("X402_PRICE_BASE_UNITS", "1000000")
os.environ.setdefault("OZ_API_KEY", "test-key-not-used-offline")


import pytest


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
