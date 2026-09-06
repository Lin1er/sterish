"""Endpoint behaviour with the chain layer stubbed out — no network needed."""

import pytest

from sterish_api import chain
from tests.conftest import SAFE_RECORD


def test_check_by_hash_returns_verdict_and_evidence(client, monkeypatch):
    monkeypatch.setattr(chain, "lookup_by_hash", lambda h: dict(SAFE_RECORD, content_hash=h))
    r = client.get("/check/by-hash/" + "a" * 64)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "SAFE" and body["is_verified"] is True
    # Rule 2 of the spec: a verdict is never served without evidence.
    assert body["evidence"]["registry_contract_id"]
    assert body["evidence"]["contract_url"].startswith("https://stellar.expert/explorer/testnet/")


def test_unknown_hash_is_404_with_is_verified_false(client, monkeypatch):
    monkeypatch.setattr(chain, "lookup_by_hash", lambda h: None)
    r = client.get("/check/by-hash/" + "c" * 64)
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "NOT_FOUND"
    # A client reading only this field must not read "unknown" as anything but unverified.
    assert body["is_verified"] is False


@pytest.mark.parametrize("bad", ["A" * 64, "abc", "g" * 64, "a" * 63, "a" * 65, ""])
def test_malformed_hash_is_400(client, bad):
    r = client.get(f"/check/by-hash/{bad}")
    assert r.status_code in (400, 404)
    if r.status_code == 400:
        assert r.json()["error"] == "INVALID_CONTENT_HASH"


def test_uppercase_hash_is_rejected_not_normalised(client, monkeypatch):
    called = []
    monkeypatch.setattr(chain, "lookup_by_hash", lambda h: called.append(h))
    r = client.get("/check/by-hash/" + "A" * 64)
    assert r.status_code == 400
    assert called == []  # never reached the chain


def test_contract_errors_map_to_the_spec_codes(client, monkeypatch):
    def raise_version_missing(skill_id, version):
        raise chain.ContractError(4)

    monkeypatch.setattr(chain, "get_version", raise_version_missing)
    r = client.get("/check/com.acme.pdf-suite/9.9.9")
    assert r.status_code == 404
    assert r.json()["error"] == "VERSION_NOT_FOUND"
    assert "9.9.9" in r.json()["detail"]

    def raise_skill_missing(skill_id):
        raise chain.ContractError(3)

    monkeypatch.setattr(chain, "query_skill", raise_skill_missing)
    r = client.get("/skills/nope")
    assert r.status_code == 404
    assert r.json()["error"] == "SKILL_NOT_FOUND"


def test_rpc_failure_is_502_never_a_default_verdict(client, monkeypatch):
    """The single most important test in this file: an unreadable chain must never
    produce a 200 with an invented verdict."""
    def boom(h):
        raise chain.ChainError("rpc down")

    monkeypatch.setattr(chain, "lookup_by_hash", boom)
    r = client.get("/check/by-hash/" + "a" * 64)
    assert r.status_code == 502
    assert r.json()["error"] == "RPC_UNAVAILABLE"
    assert "verdict" not in r.json()


def test_missing_contract_id_is_503(client, monkeypatch):
    def boom(h):
        raise chain.NotConfiguredError("REGISTRY_CONTRACT_ID is not set")

    monkeypatch.setattr(chain, "lookup_by_hash", boom)
    r = client.get("/check/by-hash/" + "a" * 64)
    assert r.status_code == 503
    assert r.json()["error"] == "NOT_CONFIGURED"


def test_skill_detail_warns_when_latest_is_not_the_audited_version(client, monkeypatch):
    monkeypatch.setattr(chain, "query_skill", lambda s: {
        "skill_id": s, "owner": "G" + "A" * 55, "versions": ["0.9.0", "0.9.3"],
        "latest_version": "0.9.3", "latest_audited_version": "0.9.0", "registered_at": 1,
    })
    monkeypatch.setattr(chain, "get_version", lambda s, v: dict(
        SAFE_RECORD, skill_id=s, version=v,
        verdict="SAFE" if v == "0.9.0" else "UNAUDITED",
        is_verified=v == "0.9.0",
    ))
    body = client.get("/skills/com.acme.pdf-suite").json()
    assert body["warning"] and "0.9.3" in body["warning"]
    # Only the audited version appears, and no skill-level verdict exists at all.
    assert [v["version"] for v in body["audited_versions"]] == ["0.9.0"]
    assert "verdict" not in body


def test_skills_list_prefixes_verdict_fields(client, monkeypatch):
    monkeypatch.setattr(chain, "query_all_skills", lambda start, limit: [{
        "skill_id": "com.acme.pdf-suite", "owner": "G" + "A" * 55,
        "versions": ["1.0.0"], "latest_version": "1.0.0",
        "latest_audited_version": "1.0.0", "registered_at": 1,
    }])
    monkeypatch.setattr(chain, "get_version", lambda s, v: SAFE_RECORD)
    monkeypatch.setattr(chain, "get_skill_count", lambda: 1)
    row = client.get("/skills").json()["skills"][0]
    # A bare `verdict` on a list row is what let a UI badge an unaudited version.
    assert "verdict" not in row
    assert row["latest_audited_verdict"] == "SAFE"
    assert row["latest_audited_is_verified"] is True


def test_health_is_503_when_chain_unreadable(client, monkeypatch):
    monkeypatch.setattr(chain, "rpc_reachable", lambda: (False, None))
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["rpc_reachable"] is False
