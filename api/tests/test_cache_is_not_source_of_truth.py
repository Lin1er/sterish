"""The index is a cache. Deleting it must not change a single verdict."""

from sterish_api import chain, indexer
from tests.conftest import SAFE_RECORD

ROW = {
    "event": "version_registered", "skill_id": SAFE_RECORD["skill_id"],
    "version": SAFE_RECORD["version"], "content_hash": SAFE_RECORD["content_hash"],
    "verdict": None, "trust_score": None, "owner": None, "auditor": None,
    "ledger": 4482508, "tx_hash": "de" * 32, "occurred_at": 1756800000,
}
AUDIT_ROW = dict(ROW, event="version_recorded", tx_hash="ab" * 32,
                 verdict="SAFE", trust_score=88)


def _verdict_fields(body):
    return {k: body[k] for k in ("skill_id", "version", "verdict", "trust_score", "is_verified")}


def test_dropping_the_cache_keeps_the_verdict_and_only_drops_tx_links(client, monkeypatch):
    monkeypatch.setattr(chain, "lookup_by_hash", lambda h: dict(SAFE_RECORD, content_hash=h))
    indexer._store([ROW, AUDIT_ROW])

    warm = client.get("/check/by-hash/" + "a" * 64).json()
    assert warm["evidence"]["registration_tx"] == "de" * 32
    assert warm["evidence"]["audit_tx"] == "ab" * 32

    indexer.rebuild()  # cache dropped

    cold = client.get("/check/by-hash/" + "a" * 64).json()
    # The answer that matters is identical...
    assert _verdict_fields(cold) == _verdict_fields(warm)
    assert cold["evidence"]["evidence_hash"] == warm["evidence"]["evidence_hash"]
    # ...only the decoration the index supplied is gone, served as null, never faked.
    assert cold["evidence"]["registration_tx"] is None
    assert cold["evidence"]["audit_tx"] is None


def test_rebuild_is_idempotent_and_restores_the_same_rows(client):
    indexer._store([ROW, AUDIT_ROW])
    before, total_before = indexer.feed()
    assert total_before == 2

    indexer.rebuild()
    assert indexer.feed()[1] == 0
    assert indexer.last_indexed_ledger() is None

    indexer._store([ROW, AUDIT_ROW])          # what a re-poll would do
    after, total_after = indexer.feed()
    assert total_after == total_before
    assert [r["tx_hash"] for r in after] == [r["tx_hash"] for r in before]


def test_storing_the_same_events_twice_is_idempotent(client):
    assert indexer._store([ROW, AUDIT_ROW]) == 2
    assert indexer._store([ROW, AUDIT_ROW]) == 0
    assert indexer.feed()[1] == 2


def test_a_broken_index_never_breaks_a_chain_answer(client, monkeypatch):
    monkeypatch.setattr(chain, "lookup_by_hash", lambda h: dict(SAFE_RECORD, content_hash=h))
    monkeypatch.setattr(indexer, "_connect", lambda: (_ for _ in ()).throw(indexer.sqlite3.Error("disk gone")))
    r = client.get("/check/by-hash/" + "a" * 64)
    assert r.status_code == 200
    assert r.json()["verdict"] == "SAFE"
    assert r.json()["evidence"]["registration_tx"] is None
