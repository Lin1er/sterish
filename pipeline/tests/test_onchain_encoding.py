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


class TestErrorNaming:
    """Error numbers collide across contracts, so the name depends on which one answered."""

    def test_the_same_number_names_a_different_error_per_contract(self):
        assert "SkillNotFound" in str(onchain.ContractCallError(3, "query_skill"))
        assert "NotOpen" in str(onchain.ContractCallError(3, "post_bond"))

    def test_escrow_functions_resolve_against_the_escrow_abi(self):
        err = onchain.ContractCallError(2, "settle")
        assert err.contract == "escrow"
        assert "RequestNotFound" in str(err)

    def test_sac_error_is_named_rather_than_reported_as_unknown(self):
        """Found live: create_audit_request surfaced the SAC's #10 through the escrow,
        and the registry-only table rendered a payer-cannot-pay failure as 'Unknown'."""
        err = onchain.ContractCallError(10, "create_audit_request")
        assert "BalanceOutOfRange" in str(err)
        assert "Unknown" not in str(err)

    def test_an_unmapped_number_still_says_unknown(self):
        assert "Unknown" in str(onchain.ContractCallError(99, "settle"))


class TestTokensErrorNaming:
    """STE-50: Tokens refusals were named from the registry's table."""

    def test_mint_license_5_is_the_verified_gate_not_a_duplicate_version(self):
        """Found by the STE-27 rehearsal: the contract refusing to licence a DANGEROUS
        version was logged as `VersionAlreadyExists (#5, registry)`."""
        err = onchain.ContractCallError(5, "mint_license")
        assert err.contract == "tokens"
        assert str(err) == "mint_license failed: NotVerified (#5, tokens)"

    def test_mint_verified_4_is_not_safe_verdict(self):
        err = onchain.ContractCallError(4, "mint_verified")
        assert "NotSafeVerdict (#4, tokens)" in str(err)

    @pytest.mark.parametrize(
        "function", ["has_license", "is_verified_token", "get_token", "total_supply",
                     "set_minter_role", "owner_of"],
    )
    def test_every_tokens_entrypoint_resolves_to_the_tokens_abi(self, function):
        assert onchain.ContractCallError(2, function).contract == "tokens"

    def test_the_tokens_table_matches_the_contract_source(self):
        """The numbers are ABI; read them from the Rust enum instead of trusting a copy."""
        import re
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2] / "contracts/tokens/src/data.rs").read_text()
        body = src[src.index("pub enum TokenError"):]
        body = body[: body.index("}")]
        from_rust = {int(n): name for name, n in re.findall(r"(\w+) = (\d+),", body)}
        assert from_rust == onchain.TOKENS_ERRORS

    def test_the_registry_table_matches_the_contract_source(self):
        """STE-44 added 10-13 to the registry; the table had stopped at 9."""
        import re
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2] / "contracts/registry/src/data.rs").read_text()
        body = src[src.index("pub enum RegistryError"):]
        body = body[: body.index("}")]
        from_rust = {int(n): name for name, n in re.findall(r"(\w+) = (\d+),", body)}
        assert from_rust == onchain.REGISTRY_ERRORS

    def test_the_escrow_table_matches_the_contract_source(self):
        import re
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2] / "contracts/escrow/src/data.rs").read_text()
        body = src[src.index("pub enum EscrowError"):]
        body = body[: body.index("}")]
        from_rust = {int(n): name for name, n in re.findall(r"(\w+) = (\d+),", body)}
        assert from_rust == onchain.ESCROW_ERRORS


TOKENS_V2 = "CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T"


class TestSharedEntrypoints:
    """`get_admin` and the upgrade functions exist on several contracts."""

    def test_a_shared_name_without_a_contract_says_it_cannot_tell(self):
        msg = str(onchain.ContractCallError(11, "propose_upgrade"))
        assert "contract not identified" in msg
        assert "registry NoPendingUpgrade" in msg
        assert "tokens Unknown" in msg  # tokens has no #11: shown, not guessed away

    def test_naming_the_contract_resolves_a_shared_name(self):
        err = onchain.ContractCallError(9, "propose_upgrade", contract="tokens")
        assert str(err) == "propose_upgrade failed: UpgradeAlreadyPending (#9, tokens)"

    def test_an_unknown_function_is_not_labelled_as_registry(self):
        err = onchain.ContractCallError(5, "some_future_fn")
        assert err.contract == "contract not identified"
        assert "registry VersionAlreadyExists" in str(err)
        assert "tokens NotVerified" in str(err)

    def test_simulate_passes_the_named_contract_to_the_error(self, monkeypatch):
        class Sim:
            error = "HostError: Error(Contract, #10)"
            results = None

        class Server:
            def simulate_transaction(self, tx):
                return Sim()

        monkeypatch.setattr(onchain, "_server", lambda cfg: Server())
        from sterish_pipeline.config import PipelineConfig

        with pytest.raises(onchain.ContractCallError) as info:
            onchain.simulate(PipelineConfig(), TOKENS_V2, "execute_upgrade", contract="tokens")
        assert "UpgradeNotReady (#10, tokens)" in str(info.value)
