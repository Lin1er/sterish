"""Runtime configuration, read once at import time.

Spec: docs/api-spec.md section 6 ("Config"). Starting without a registry contract id
must fail loudly rather than silently falling back to mock data, which is exactly
what the scaffold's client.py did.
"""

import os
from dataclasses import dataclass

TESTNET_PASSPHRASE = "Test SDF Network ; September 2015"
PUBLIC_PASSPHRASE = "Public Global Stellar Network ; September 2015"

# Contract error numbers are part of the frozen ABI (contracts/registry/src/data.rs).
# Never renumber; the API maps them onto the HTTP errors in api-spec.md section 4.
REGISTRY_ERR_NOT_INITIALIZED = 1
REGISTRY_ERR_SKILL_NOT_FOUND = 3
REGISTRY_ERR_VERSION_NOT_FOUND = 4


@dataclass(frozen=True)
class Settings:
    registry_contract_id: str
    rpc_url: str
    network_passphrase: str
    db_path: str
    rate_limit_per_minute: int
    indexer_enabled: bool
    indexer_poll_seconds: int
    # getEvents only scans a bounded window forward from start_ledger. Measured against
    # soroban-testnet on 2026-09-04: a start 5_000 ledgers before a known event still
    # returned it, 10_000 before returned nothing. The indexer therefore walks forward
    # in chunks rather than asking for the whole retained history in one call.
    indexer_chunk_ledgers: int
    report_base_url: str

    @property
    def network(self) -> str:
        if self.network_passphrase == TESTNET_PASSPHRASE:
            return "testnet"
        if self.network_passphrase == PUBLIC_PASSPHRASE:
            return "public"
        return "unknown"

    @property
    def explorer_base(self) -> str:
        """stellar.expert base for this network. Never hardcode one (api-spec section 2)."""
        return f"https://stellar.expert/explorer/{'public' if self.network == 'public' else 'testnet'}"

    def contract_url(self, contract_id: str) -> str:
        return f"{self.explorer_base}/contract/{contract_id}"

    def tx_url(self, tx_hash: str) -> str:
        return f"{self.explorer_base}/tx/{tx_hash}"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc


def load_settings() -> Settings:
    # REGISTRY_CONTRACT_ID is the name the spec uses; REGISTRY_CA is what the repo's
    # deploy scripts and .env already write (docs/deployments.md). Accept both so the
    # API runs against the existing .env without a rename.
    contract_id = (
        os.getenv("REGISTRY_CONTRACT_ID") or os.getenv("REGISTRY_CA") or ""
    ).strip()
    return Settings(
        registry_contract_id=contract_id,
        rpc_url=os.getenv("STELLAR_RPC_URL", "https://soroban-testnet.stellar.org").strip(),
        network_passphrase=os.getenv("STELLAR_NETWORK_PASSPHRASE", TESTNET_PASSPHRASE),
        db_path=os.getenv("STERISH_DB_PATH", "sterish_index.db"),
        rate_limit_per_minute=_env_int("RATE_LIMIT_PER_MINUTE", 100),
        indexer_enabled=os.getenv("INDEXER_ENABLED", "1") not in ("0", "false", "False"),
        indexer_poll_seconds=_env_int("INDEXER_POLL_SECONDS", 8),
        indexer_chunk_ledgers=_env_int("INDEXER_CHUNK_LEDGERS", 4000),
        report_base_url=os.getenv("REPORT_BASE_URL", "").rstrip("/"),
    )


settings = load_settings()
