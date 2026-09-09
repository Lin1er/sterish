"""Integration tests against the live testnet deployment from STE-13.

Opt-in: they need network and the deployed contract, so they are skipped unless
STERISH_LIVE_TESTS=1. Run them with the repo .env loaded:

    set -a && . ./.env && set +a
    cd api && STERISH_LIVE_TESTS=1 uv run --extra dev pytest tests/test_live_testnet.py -v
"""

import os

import pytest

from sterish_api import chain, indexer

pytestmark = pytest.mark.skipif(
    os.getenv("STERISH_LIVE_TESTS") != "1",
    reason="set STERISH_LIVE_TESTS=1 (and load .env) to run against testnet",
)

SAFE_ID = os.getenv("SAFE_SKILL_ID", "com.sterish.weather-lookup")
SAFE_HASH = os.getenv("SAFE_HASH", "")
POISON_ID = os.getenv("POISON_SKILL_ID", "com.evil.token-drainer")
POISON_HASH = os.getenv("POISON_HASH", "")


def test_the_poisoned_skill_reads_back_dangerous_from_chain(client):
    """The claim the whole project rests on, verified against the ledger."""
    body = client.get(f"/check/by-hash/{POISON_HASH}").json()
    assert body["skill_id"] == POISON_ID
    assert body["verdict"] == "DANGEROUS"
    assert body["is_verified"] is False


def test_the_safe_skill_reads_back_safe_from_chain(client):
    body = client.get(f"/check/by-hash/{SAFE_HASH}").json()
    assert body["skill_id"] == SAFE_ID
    assert body["verdict"] == "SAFE"
    assert body["is_verified"] is True
    assert 0 <= body["trust_score"] <= 100


def test_one_flipped_byte_misses_the_index(client):
    """A poisoned v2 cannot inherit v1's badge: change one byte, get a 404."""
    flipped = ("0" if SAFE_HASH[0] != "0" else "1") + SAFE_HASH[1:]
    r = client.get(f"/check/by-hash/{flipped}")
    assert r.status_code == 404
    assert r.json()["is_verified"] is False


def test_by_name_and_by_hash_agree(client):
    by_hash = client.get(f"/check/by-hash/{SAFE_HASH}").json()
    by_name = client.get(f"/check/{SAFE_ID}/{by_hash['version']}").json()
    for field in ("skill_id", "version", "content_hash", "verdict", "trust_score", "is_verified"):
        assert by_hash[field] == by_name[field]


def test_skills_list_contains_the_seeded_corpus(client):
    body = client.get("/skills?limit=100").json()
    ids = {s["skill_id"] for s in body["skills"]}
    assert {SAFE_ID, POISON_ID} <= ids
    assert body["total"] >= 2


def test_indexer_supplies_clickable_tx_links(client):
    """End-to-end: poll the chain, then confirm the evidence links resolve to real
    transactions rather than staying null."""
    indexer.rebuild()
    indexer.poll_once()

    evidence = client.get(f"/check/by-hash/{POISON_HASH}").json()["evidence"]
    assert evidence["registration_tx"] and len(evidence["registration_tx"]) == 64
    assert evidence["audit_tx"] and len(evidence["audit_tx"]) == 64
    assert evidence["audit_tx_url"].startswith("https://stellar.expert/explorer/testnet/tx/")


def test_check_still_correct_with_the_cache_dropped(client):
    """Requirement from STE-17: turn the cache off and /check must stay correct,
    because it is answered by RPC, not by the index."""
    indexer.rebuild()
    indexer.poll_once()
    warm = client.get(f"/check/by-hash/{POISON_HASH}").json()

    indexer.rebuild()
    cold = client.get(f"/check/by-hash/{POISON_HASH}").json()

    assert cold["verdict"] == warm["verdict"] == "DANGEROUS"
    assert cold["trust_score"] == warm["trust_score"]
    assert cold["evidence"]["registration_tx"] is None  # only the decoration is lost


def test_rebuild_from_chain_is_consistent(client):
    """Drop -> rebuild -> same rows. This is the documented recovery procedure."""
    indexer.rebuild()
    indexer.poll_once()
    first, total_first = indexer.feed(limit=200)
    assert total_first > 0

    indexer.rebuild()
    assert indexer.feed()[1] == 0

    indexer.poll_once()
    second, total_second = indexer.feed(limit=200)
    assert total_second == total_first
    assert {r["tx_hash"] for r in second} == {r["tx_hash"] for r in first}


def test_health_reports_a_reachable_chain(client):
    body = client.get("/health").json()
    assert body["rpc_reachable"] is True
    assert body["network"] == "testnet"
    assert body["registry_contract_id"].startswith("C")


def test_rpc_reachable_probe():
    reachable, latest = chain.rpc_reachable()
    assert reachable is True and latest and latest > 0


# --- GET /license against the deployed tokens contract (STE-35) ---------------

# The buyer from the STE-19 x402 run. It holds a licence for SAFE_ID@1.0.0, minted
# on chain, so this is a real held/not-held pair rather than two mocked booleans.
LICENSED_AGENT = os.getenv("DEVELOPER_ADDRESS", "")
UNLICENSED_AGENT = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"


def test_license_status_reads_the_deployed_tokens_contract(client):
    """The endpoint is only worth anything if it maps to the live view function."""
    body = client.get(f"/license/{SAFE_ID}/1.0.0?agent={UNLICENSED_AGENT}").json()
    assert body["held"] is False
    assert body["agent"] == UNLICENSED_AGENT
    assert body["tokens_contract_id"].startswith("C")
    assert body["contract_url"].endswith(body["tokens_contract_id"])


def test_license_agrees_with_the_paid_path(client):
    """/use and /license must never disagree about the same (agent, skill, version).

    They read the same contract function; if they diverge, one of them is lying to a
    dashboard about whether someone already paid.
    """
    if not LICENSED_AGENT:
        pytest.skip("DEVELOPER_ADDRESS not in the environment")

    held = client.get(f"/license/{SAFE_ID}/1.0.0?agent={LICENSED_AGENT}").json()["held"]
    use = client.get(f"/use/{SAFE_ID}/1.0.0", headers={"X-AGENT-ADDRESS": LICENSED_AGENT})
    # /use answers 200 with the artifact when the licence is held, 402 when it is not.
    assert held is (use.status_code == 200), (
        f"/license says held={held} but /use returned {use.status_code}"
    )


def test_license_answers_for_a_dangerous_version(client):
    """The case /use cannot answer at all: it returns 403 before checking the licence."""
    body = client.get(f"/license/{POISON_ID}/1.0.0?agent={UNLICENSED_AGENT}").json()
    assert body["held"] is False
    assert client.get(f"/use/{POISON_ID}/1.0.0").status_code == 403


def test_license_answers_for_a_skill_with_no_artifact_on_disk(client):
    """46 of 47 live skills have no artifact; /use 404s on those even when licensed."""
    body = client.get(f"/license/com.sterish.e2e-1788541421/1.0.0?agent={UNLICENSED_AGENT}")
    assert body.status_code == 200
    assert body.json()["held"] is False
