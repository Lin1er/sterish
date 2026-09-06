"""Event decoding + the two RPC quirks the indexer has to survive."""

from unittest.mock import Mock

from stellar_sdk import Address, scval

from sterish_api import indexer

G = "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU"
HASH = bytes.fromhex("c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0")


def _event(topics, value, successful=True, ledger=4482518, tx="ab" * 32):
    ev = Mock()
    ev.topic = [
        scval.to_symbol(t).to_xdr()
        if isinstance(t, str) and t.islower() and "." not in t
        else scval.to_string(t).to_xdr()
        for t in topics
    ]
    ev.value = value.to_xdr()
    ev.ledger = ledger
    ev.transaction_hash = tx
    ev.in_successful_contract_call = successful
    ev.ledger_close_at = "2026-09-03T11:49:37Z"
    return ev


def test_version_recorded_decodes_to_indexable_row():
    value = scval.to_map({
        scval.to_symbol("content_hash"): scval.to_bytes(HASH),
        scval.to_symbol("verdict"): scval.to_vec([scval.to_symbol("Dangerous")]),
        scval.to_symbol("trust_score"): scval.to_uint32(5),
        scval.to_symbol("auditor"): scval.to_address(Address(G)),
    })
    event = _event(["version_recorded", "com.evil.token-drainer", "1.0.0"], value)
    row = indexer._decode_event(event)
    assert row["event"] == "version_recorded"
    assert row["skill_id"] == "com.evil.token-drainer"
    assert row["version"] == "1.0.0"
    assert row["verdict"] == "DANGEROUS"
    assert row["trust_score"] == 5
    assert row["auditor"] == G
    assert row["content_hash"] == HASH.hex()
    assert row["occurred_at"] == 1788436177


def test_events_from_failed_calls_are_not_indexed():
    value = scval.to_map({scval.to_symbol("owner"): scval.to_address(Address(G))})
    ev = _event(["skill_registered", "com.evil.token-drainer"], value, successful=False)
    assert indexer._decode_event(ev) is None


def test_untracked_events_are_ignored():
    value = scval.to_map({scval.to_symbol("owner"): scval.to_address(Address(G))})
    assert indexer._decode_event(_event(["something_else", "x"], value)) is None


def test_versionless_event_stores_empty_string_so_dedupe_works():
    """SQLite treats NULLs as distinct in a UNIQUE constraint, so a NULL version would
    let overlapping polls insert the same skill_registered row twice."""
    value = scval.to_map({scval.to_symbol("owner"): scval.to_address(Address(G))})
    row = indexer._decode_event(_event(["skill_registered", "com.evil.token-drainer"], value))
    assert row["version"] == ""

    assert indexer._store([row]) == 1
    assert indexer._store([row]) == 0          # the duplicate is rejected
    assert indexer.feed()[1] == 1
