"""Decoding of on-chain values. Every expectation here was confirmed against the live
registry on testnet (see the probe notes in chain.py) rather than assumed from docs."""

from stellar_sdk import Address

from sterish_api.chain import (
    address_str,
    decode_skill_entry,
    decode_verdict,
    decode_version_record,
)

ZERO = bytes(32)
G = "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU"


def test_enum_decodes_from_one_element_list():
    # soroban unit variants arrive as ['Safe'], not 'Safe'.
    assert decode_verdict(["Safe"]) == "SAFE"
    assert decode_verdict(["Dangerous"]) == "DANGEROUS"
    assert decode_verdict(["Warning"]) == "WARNING"
    assert decode_verdict(["Unaudited"]) == "UNAUDITED"


def test_unknown_verdict_falls_back_to_unaudited_not_safe():
    # The whole point of the service: never invent a SAFE.
    for junk in (None, [], ["Nonsense"], "", 7):
        assert decode_verdict(junk) == "UNAUDITED"


def test_address_renders_as_strkey_not_repr():
    assert address_str(Address(G)) == G
    assert address_str(None) is None


def test_zero_evidence_hash_is_served_as_null():
    record = decode_version_record({
        "skill_id": "s", "version": "1", "content_hash": bytes.fromhex("aa" * 32),
        "verdict": ["Unaudited"], "trust_score": 0, "owner": Address(G),
        "auditor": None, "registered_at": 10, "audited_at": 0, "evidence_hash": ZERO,
    })
    assert record["evidence_hash"] is None
    assert record["audited_at"] is None      # 0 is served as null, not 0
    assert record["auditor"] is None
    assert record["is_verified"] is False


def test_is_verified_only_for_safe():
    def verdict(name):
        return decode_version_record({
            "skill_id": "s", "version": "1", "content_hash": ZERO, "verdict": [name],
            "trust_score": 99, "owner": Address(G), "auditor": Address(G),
            "registered_at": 1, "audited_at": 2, "evidence_hash": bytes.fromhex("bb" * 32),
        })["is_verified"]

    assert verdict("Safe") is True
    # A 99 trust score with a WARNING verdict must still not be "verified".
    assert verdict("Warning") is False
    assert verdict("Dangerous") is False
    assert verdict("Unaudited") is False


def test_skill_entry_has_no_verdict_field():
    entry = decode_skill_entry({
        "skill_id": "s", "owner": Address(G), "versions": ["1", "2"],
        "latest_version": "2", "latest_audited_version": "1", "registered_at": 5,
    })
    assert "verdict" not in entry and "trust_score" not in entry
    assert entry["versions"] == ["1", "2"]
