import os
from typing import Any

import httpx

STELLAR_RPC_URL = os.getenv("STELLAR_RPC_URL", "https://soroban-testnet.stellar.org")
REGISTRY_CONTRACT_ID = os.getenv("REGISTRY_CONTRACT_ID", "")


async def invoke_contract(contract_id: str, function: str, args: list[str]) -> dict[str, Any]:
    """Invoke a Soroban contract read-only function via RPC."""
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "simulateTransaction",
        "params": {
            "transaction": {
                "source": "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
                "fee": "100",
                "seq": "0",
                "operations": [
                    {
                        "type": "invoke_host_function",
                        "function": function,
                        "args": {"address": contract_id, "args": args},
                    }
                ],
                "xdr": "",
            },
            "resource_fee": "0",
        },
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(STELLAR_RPC_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            return {}
        return data.get("result", {}).get("results", [{}])[0].get("xdr", {})


def query_skill(skill_id: str) -> dict[str, Any] | None:
    """Query a skill from the on-chain registry. Returns mock data if no contract deployed."""
    if not REGISTRY_CONTRACT_ID:
        return _mock_skills().get(skill_id)
    # TODO: implement real RPC call via stellar-sdk when contract is deployed
    return _mock_skills().get(skill_id)


def query_all_skills(start: int, limit: int) -> list[dict[str, Any]]:
    """Query paginated skills from the on-chain registry."""
    skills = list(_mock_skills().values())
    return skills[start : start + limit]


def query_skill_count() -> int:
    """Get total number of registered skills."""
    return len(_mock_skills())


def _mock_skills() -> dict[str, dict[str, Any]]:
    """Mock data for development before contract deployment."""
    return {
        "skill-001": {
            "skill_id": "skill-001",
            "name": "web-search-tool",
            "latest_verdict": "SAFE",
            "trust_score": 92,
            "evidence_url": "https://stellar.expert/testnet/tx/0xabc123",
            "audit_timestamp": "2026-08-20T14:30:00Z",
            "auditor": "GCBYXEE...",
            "versions": [
                {"version": "1.0.0", "content_hash": "abc123...", "registered_at": 1692537000}
            ],
        },
        "skill-002": {
            "skill_id": "skill-002",
            "name": "file-manager",
            "latest_verdict": "WARNING",
            "trust_score": 65,
            "evidence_url": "",
            "audit_timestamp": "2026-08-22T10:00:00Z",
            "auditor": "GCBYXEE...",
            "versions": [
                {"version": "1.2.0", "content_hash": "def456...", "registered_at": 1692708800}
            ],
        },
    }
