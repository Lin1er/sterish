"""Event decoding + the two RPC quirks the indexer has to survive."""

from unittest.mock import Mock

from stellar_sdk import Address, scval

from sterish_api import indexer
from sterish_api.config import settings

G = "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU"
HASH = bytes.fromhex("c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0")


def _event(topics, value, successful=True, ledger=4482518, tx="ab" * 32, contract_id=None):
    ev = Mock()
    ev.contract_id = contract_id or settings.registry_contract_id
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
    event = _event(["version_recorded", "com.fixtures.poisoned.token-drainer", "1.0.0"], value)
    row = indexer._decode_event(event)
    assert row["event"] == "version_recorded"
    assert row["skill_id"] == "com.fixtures.poisoned.token-drainer"
    assert row["version"] == "1.0.0"
    assert row["verdict"] == "DANGEROUS"
    assert row["trust_score"] == 5
    assert row["auditor"] == G
    assert row["content_hash"] == HASH.hex()
    assert row["occurred_at"] == 1788436177


def test_events_from_failed_calls_are_not_indexed():
    value = scval.to_map({scval.to_symbol("owner"): scval.to_address(Address(G))})
    ev = _event(
        ["skill_registered", "com.fixtures.poisoned.token-drainer"], value, successful=False
    )
    assert indexer._decode_event(ev) is None


def test_untracked_events_are_ignored():
    value = scval.to_map({scval.to_symbol("owner"): scval.to_address(Address(G))})
    assert indexer._decode_event(_event(["something_else", "x"], value)) is None


def test_versionless_event_stores_empty_string_so_dedupe_works():
    """SQLite treats NULLs as distinct in a UNIQUE constraint, so a NULL version would
    let overlapping polls insert the same skill_registered row twice."""
    value = scval.to_map({scval.to_symbol("owner"): scval.to_address(Address(G))})
    row = indexer._decode_event(
        _event(["skill_registered", "com.fixtures.poisoned.token-drainer"], value)
    )
    assert row["version"] == ""

    assert indexer._store([row]) == 1
    assert indexer._store([row]) == 0          # the duplicate is rejected
    assert indexer.feed()[1] == 1


# --- STE-46: license_minted from the tokens contract -------------------------------------


def _license_event(contract_id=None, agent=G):
    value = scval.to_map({scval.to_symbol("agent"): scval.to_address(Address(agent))})
    return _event(
        ["license_minted", "com.acme.pdf-suite", "1.0.0"], value,
        contract_id=contract_id or settings.tokens_contract_id,
    )


def test_license_minted_decodes_to_a_license_row():
    row = indexer._decode_event(_license_event())
    assert row == {
        "_license": {
            "tokens_contract_id": settings.tokens_contract_id,
            "agent": G,
            "skill_id": "com.acme.pdf-suite",
            "version": "1.0.0",
            "ledger": 4482518,
            "tx_hash": "ab" * 32,
            "occurred_at": row["_license"]["occurred_at"],
        }
    }


def test_license_minted_from_another_contract_is_ignored():
    """The filter lists our contracts, but a decoder must not trust that alone."""
    other = "CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA"
    assert indexer._decode_event(_license_event(contract_id=other)) is None


def test_a_registry_event_name_from_the_tokens_contract_never_reaches_the_feed():
    value = scval.to_map({scval.to_symbol("owner"): scval.to_address(Address(G))})
    ev = _event(["skill_registered", "com.acme.pdf-suite"], value,
                contract_id=settings.tokens_contract_id)
    assert indexer._decode_event(ev) is None
