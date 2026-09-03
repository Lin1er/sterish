"""Registry reads for the verification API.

Until the registry contract is deployed (STERISH-9) and the real Soroban reads
land (STERISH-13), this module serves a small fixture registry so the API, its
tests, and the dashboard have something concrete to talk to.

Fixture mode is active only while `REGISTRY_CONTRACT_ID` is unset. Once a
contract ID is configured the fixtures are never consulted.
"""

import os
from typing import Any

STELLAR_RPC_URL = os.getenv("STELLAR_RPC_URL", "https://soroban-testnet.stellar.org")
STELLAR_NETWORK_PASSPHRASE = os.getenv(
    "STELLAR_NETWORK_PASSPHRASE", "Test SDF Network ; September 2015"
)
REGISTRY_CONTRACT_ID = os.getenv("REGISTRY_CONTRACT_ID", "")


def fixture_mode() -> bool:
    """True while no registry contract is configured."""
    return not os.getenv("REGISTRY_CONTRACT_ID", "")


def query_skill(skill_id: str) -> dict[str, Any] | None:
    """Return a single skill entry, or None when it is not registered."""
    if fixture_mode():
        return _fixture_skills().get(skill_id)
    raise NotImplementedError(
        "on-chain registry reads land in STERISH-13; unset REGISTRY_CONTRACT_ID to use fixture mode"
    )


def query_all_skills(start: int, limit: int) -> list[dict[str, Any]]:
    """Return a page of registered skills."""
    if fixture_mode():
        return list(_fixture_skills().values())[start : start + limit]
    raise NotImplementedError(
        "on-chain registry reads land in STERISH-13; unset REGISTRY_CONTRACT_ID to use fixture mode"
    )


def query_skill_count() -> int:
    """Total number of registered skills."""
    if fixture_mode():
        return len(_fixture_skills())
    raise NotImplementedError(
        "on-chain registry reads land in STERISH-13; unset REGISTRY_CONTRACT_ID to use fixture mode"
    )


def _fixture_skills() -> dict[str, dict[str, Any]]:
    """Fixture registry used before a contract is deployed."""
    return {
        "com.example.web-search": {
            "skill_id": "com.example.web-search",
            "latest_verdict": "SAFE",
            "trust_score": 92,
            "evidence_hash": "a" * 64,
            "evidence_url": "",
            "audit_timestamp": 1755700200,
            "auditor": "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
            "versions": [
                {
                    "version": "1.0.0",
                    "content_hash": "b" * 64,
                    "registered_at": 1755613800,
                }
            ],
        },
        "com.example.file-manager": {
            "skill_id": "com.example.file-manager",
            "latest_verdict": "WARNING",
            "trust_score": 65,
            "evidence_hash": "c" * 64,
            "evidence_url": "",
            "audit_timestamp": 1755872000,
            "auditor": "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
            "versions": [
                {
                    "version": "1.2.0",
                    "content_hash": "d" * 64,
                    "registered_at": 1755785600,
                }
            ],
        },
        "com.evil.token-drainer": {
            "skill_id": "com.evil.token-drainer",
            "latest_verdict": "DANGEROUS",
            "trust_score": 4,
            "evidence_hash": "e" * 64,
            "evidence_url": "",
            "audit_timestamp": 1755958400,
            "auditor": "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
            "versions": [
                {
                    "version": "1.0.0",
                    "content_hash": "f" * 64,
                    "registered_at": 1755872000,
                }
            ],
        },
    }
