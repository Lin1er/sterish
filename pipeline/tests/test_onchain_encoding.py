"""Argument encoding for the frozen registry ABI.

The scaffold got all of this wrong and nothing caught it, because nothing imported
the module. These tests pin the shapes that were proven by simulation against the
deployed contract (see onchain.py's docstring for the evidence table).
"""

import pytest
from stellar_sdk import scval
from stellar_sdk import xdr as stellar_xdr

from sterish_pipeline import onchain
from sterish_pipeline.models import FinalVerdict


def _native(val):
    return scval.to_native(val)


def test_verdict_encodes_as_a_one_element_symbol_vec():
    """A bare symbol or a u32 is rejected by the host with InvalidAction."""
    encoded = onchain.verdict_scval(FinalVerdict.SAFE)
    assert encoded.type == stellar_xdr.SCValType.SCV_VEC
    assert _native(encoded) == ["Safe"]


@pytest.mark.parametrize("given,expected", [
    (FinalVerdict.SAFE, "Safe"),
    (FinalVerdict.DANGEROUS, "Dangerous"),
    (FinalVerdict.WARNING, "Warning"),
    ("SAFE", "Safe"),
    ("UNAUDITED", "Unaudited"),
])
def test_every_variant_maps_to_the_rust_spelling(given, expected):
    assert _native(onchain.verdict_scval(given)) == [expected]


def test_a_non_variant_is_rejected_before_it_reaches_the_chain():
    with pytest.raises(ValueError, match="not an AuditVerdict variant"):
        onchain.verdict_scval("PROBABLY_FINE")


def test_evidence_hash_must_be_exactly_32_bytes():
    onchain.hash_scval("ab" * 32)                      # accepted
    with pytest.raises(ValueError, match="expected 32 bytes"):
        onchain.hash_scval("ab" * 16)
    with pytest.raises(ValueError, match="expected 32 bytes"):
        onchain.hash_scval("ab" * 64)


def test_contract_error_carries_the_frozen_abi_number():
    err = onchain.ContractCallError(4, "submit_verdict")
    assert err.code == 4
    assert "VersionNotFound" in str(err)
    # The numbers are the public ABI; a rename here would silently mislabel failures.
    assert onchain.REGISTRY_ERRORS[3] == "SkillNotFound"
    assert onchain.REGISTRY_ERRORS[6] == "HashAlreadyRegistered"
