"""On-chain submission: argument encoding and orchestrator flow.

These run with no network. The encoding tests pin the exact ScVal bytes against
the contract ABI — this is where the scaffold's u32-vs-enum verdict bug is
caught and kept from coming back. The orchestrator tests drive the full
register -> verdict -> settle/slash flow against a fake ChainClient that records
calls, so the ordering and idempotency logic is exercised without a live chain.

Live-testnet execution (real tx hashes, stellar.expert links) is gated on the
contract being deployed (STERISH-9 / STE-13) and lives in the integration test
that is skipped until STERISH_REGISTRY_CONTRACT_ID is set.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import pytest
from stellar_sdk import Keypair, scval
from stellar_sdk.xdr import SCVal

from sterish_pipeline.models import FinalVerdict
from sterish_pipeline.onchain import (
    VERDICT_TO_VARIANT,
    ChainClient,
    OnChainError,
    RetryPolicy,
    VerdictOrchestrator,
    encode_register_skill_args,
    encode_submit_verdict_args,
    encode_verdict,
    submit_verdict_to_chain,
)

A_HASH = "aa" * 32
E_HASH = "bb" * 32
AUDITOR = Keypair.random()


class TestVerdictEncoding:
    def test_verdict_is_an_enum_not_a_u32(self) -> None:
        # The bug: to_uint32(2). The fix: the AuditVerdict enum variant.
        enum_xdr = encode_verdict(FinalVerdict.SAFE).to_xdr()
        assert enum_xdr == scval.to_enum("Safe", None).to_xdr()
        assert enum_xdr != scval.to_uint32(2).to_xdr()

    @pytest.mark.parametrize(
        ("verdict", "variant"),
        [
            (FinalVerdict.SAFE, "Safe"),
            (FinalVerdict.DANGEROUS, "Dangerous"),
            (FinalVerdict.WARNING, "Warning"),
        ],
    )
    def test_each_verdict_maps_to_its_variant(self, verdict: FinalVerdict, variant: str) -> None:
        assert encode_verdict(verdict).to_xdr() == scval.to_enum(variant, None).to_xdr()
        assert VERDICT_TO_VARIANT[verdict] == variant

    def test_enum_decodes_back_to_the_variant_name(self) -> None:
        parsed_key, parsed_data = scval.from_enum(encode_verdict(FinalVerdict.DANGEROUS))
        assert parsed_key == "Dangerous"
        assert parsed_data is None


class TestArgumentEncoding:
    def test_register_skill_arg_types(self) -> None:
        args = encode_register_skill_args(AUDITOR.public_key, "com.x.demo", "1.0.0", A_HASH)
        assert [a.type.value for a in args] == [
            scval.to_address(AUDITOR.public_key).type.value,
            scval.to_string("x").type.value,
            scval.to_string("x").type.value,
            scval.to_bytes(b"x").type.value,
        ]

    def test_submit_verdict_arg_shapes(self) -> None:
        args = encode_submit_verdict_args("com.x.demo", "1.0.0", FinalVerdict.SAFE, 85, E_HASH)
        assert len(args) == 5
        assert args[0].to_xdr() == scval.to_string("com.x.demo").to_xdr()
        assert args[1].to_xdr() == scval.to_string("1.0.0").to_xdr()
        assert args[2].to_xdr() == scval.to_enum("Safe", None).to_xdr()
        assert args[3].to_xdr() == scval.to_uint32(85).to_xdr()
        assert args[4].to_xdr() == scval.to_bytes(bytes.fromhex(E_HASH)).to_xdr()

    def test_evidence_hash_must_be_32_bytes(self) -> None:
        with pytest.raises(OnChainError, match="32 bytes"):
            encode_submit_verdict_args("s", "1.0.0", FinalVerdict.SAFE, 10, "aa")

    def test_score_is_bounds_checked(self) -> None:
        with pytest.raises(OnChainError, match="0..=100"):
            encode_submit_verdict_args("s", "1.0.0", FinalVerdict.SAFE, 101, E_HASH)

    def test_bad_hex_is_rejected(self) -> None:
        with pytest.raises((OnChainError, ValueError)):
            encode_submit_verdict_args("s", "1.0.0", FinalVerdict.SAFE, 10, "zz" * 32)


class FakeChainClient:
    """Records invoke/read calls; returns canned tx hashes and read results."""

    def __init__(self, registered_ids: set[str] | None = None) -> None:
        self.invocations: list[tuple[str, str, Sequence[SCVal]]] = []
        self.reads: list[tuple[str, str]] = []
        self._registered = registered_ids or set()
        self._counter = 0

    def invoke(
        self, contract_id: str, function: str, args: Sequence[SCVal], signer: Keypair
    ) -> str:
        self.invocations.append((contract_id, function, args))
        self._counter += 1
        return f"txhash{self._counter:04d}"

    def read(self, contract_id: str, function: str, args: Sequence[SCVal]) -> SCVal | None:
        self.reads.append((contract_id, function))
        skill_id = scval.from_string(args[0]).decode() if args else ""
        return scval.to_uint32(1) if skill_id in self._registered else None

    def functions(self) -> list[str]:
        return [fn for _, fn, _ in self.invocations]


def _orch(client: ChainClient, escrow: str = "CESCROW") -> VerdictOrchestrator:
    return VerdictOrchestrator(
        client=client,
        registry_contract_id="CREGISTRY",
        escrow_contract_id=escrow,
        auditor=AUDITOR,
        retry=RetryPolicy(attempts=1, backoff_seconds=0),
    )


class TestOrchestratorFlow:
    def test_safe_new_skill_registers_verdicts_and_settles(self) -> None:
        client = FakeChainClient()
        result = _orch(client).submit_audit(
            skill_id="com.x.safe",
            version="1.0.0",
            verdict=FinalVerdict.SAFE,
            score=90,
            evidence_hash=E_HASH,
            content_hash=A_HASH,
            request_id=1,
        )
        assert client.functions() == ["register_skill", "submit_verdict", "settle"]
        assert result.registered is True
        assert result.register_tx and result.verdict_tx and result.settle_tx
        assert result.slash_tx == ""

    def test_already_registered_skill_skips_register(self) -> None:
        client = FakeChainClient(registered_ids={"com.x.known"})
        result = _orch(client).submit_audit(
            skill_id="com.x.known",
            version="2.0.0",
            verdict=FinalVerdict.SAFE,
            score=88,
            evidence_hash=E_HASH,
            content_hash=A_HASH,
            request_id=2,
        )
        assert "register_skill" not in client.functions()
        assert result.registered is False
        assert any("already registered" in s for s in result.steps)

    def test_dangerous_skill_never_mints_or_settles(self) -> None:
        client = FakeChainClient()
        result = _orch(client).submit_audit(
            skill_id="com.evil.x",
            version="1.0.0",
            verdict=FinalVerdict.DANGEROUS,
            score=5,
            evidence_hash=E_HASH,
            content_hash=A_HASH,
            request_id=3,
        )
        assert "settle" not in client.functions()
        assert "slash" not in client.functions()
        assert result.settle_tx == "" and result.slash_tx == ""

    def test_dangerous_skill_slashes_when_asked(self) -> None:
        client = FakeChainClient()
        result = _orch(client).submit_audit(
            skill_id="com.evil.x",
            version="1.0.0",
            verdict=FinalVerdict.DANGEROUS,
            score=5,
            evidence_hash=E_HASH,
            content_hash=A_HASH,
            request_id=3,
            slash_on_dangerous=True,
        )
        assert client.functions() == ["register_skill", "submit_verdict", "slash"]
        assert result.slash_tx

    def test_no_request_id_means_no_escrow_action(self) -> None:
        client = FakeChainClient()
        _orch(client).submit_audit(
            skill_id="com.x.safe",
            version="1.0.0",
            verdict=FinalVerdict.SAFE,
            score=90,
            evidence_hash=E_HASH,
            content_hash=A_HASH,
            request_id=None,
        )
        assert client.functions() == ["register_skill", "submit_verdict"]

    def test_settle_without_escrow_configured_raises(self) -> None:
        orch = VerdictOrchestrator(
            client=FakeChainClient(),
            registry_contract_id="CREGISTRY",
            escrow_contract_id="",
            auditor=AUDITOR,
        )
        with pytest.raises(OnChainError, match="escrow"):
            orch.settle(1)


class TestRetryAndErrors:
    def test_missing_auditor_key_is_rejected(self) -> None:
        orch = VerdictOrchestrator(
            client=FakeChainClient(), registry_contract_id="CREGISTRY", auditor=None
        )
        with pytest.raises(OnChainError, match="auditor keypair"):
            orch.submit_verdict("s", "1.0.0", FinalVerdict.SAFE, 10, E_HASH)

    def test_invoke_is_retried_then_raises(self) -> None:
        class AlwaysFails:
            def invoke(self, *a, **k) -> str:
                raise RuntimeError("rpc down")

            def read(self, *a, **k):
                return None

        orch = VerdictOrchestrator(
            client=AlwaysFails(),
            registry_contract_id="CREGISTRY",
            auditor=AUDITOR,
            retry=RetryPolicy(attempts=3, backoff_seconds=0),
        )
        with pytest.raises(OnChainError, match="after 3 attempts"):
            orch.submit_verdict("s", "1.0.0", FinalVerdict.SAFE, 10, E_HASH)

    def test_transient_failure_then_success(self) -> None:
        class FlakyClient:
            def __init__(self) -> None:
                self.calls = 0

            def invoke(self, *a, **k) -> str:
                self.calls += 1
                if self.calls < 2:
                    raise RuntimeError("temporary")
                return "txok"

            def read(self, *a, **k):
                return None

        orch = VerdictOrchestrator(
            client=FlakyClient(),
            registry_contract_id="CREGISTRY",
            auditor=AUDITOR,
            retry=RetryPolicy(attempts=3, backoff_seconds=0),
        )
        assert orch.submit_verdict("s", "1.0.0", FinalVerdict.SAFE, 10, E_HASH) == "txok"

    def test_registry_id_is_required(self) -> None:
        with pytest.raises(OnChainError, match="registry_contract_id"):
            VerdictOrchestrator(client=FakeChainClient(), registry_contract_id="")


class TestBackwardsCompatibleHelper:
    def test_submit_verdict_to_chain_uses_injected_client(self) -> None:
        client = FakeChainClient()
        tx = submit_verdict_to_chain(
            contract_id="CREGISTRY",
            skill_id="com.x.demo",
            version="1.0.0",
            verdict=FinalVerdict.SAFE,
            score=90,
            evidence_hash=E_HASH,
            secret_key=AUDITOR.secret,
            client=client,
        )
        assert tx.startswith("txhash")
        assert client.functions() == ["submit_verdict"]

    def test_mismatched_public_key_is_rejected(self) -> None:
        with pytest.raises(OnChainError, match="does not match"):
            submit_verdict_to_chain(
                contract_id="CREGISTRY",
                skill_id="s",
                version="1.0.0",
                verdict=FinalVerdict.SAFE,
                score=90,
                evidence_hash=E_HASH,
                secret_key=AUDITOR.secret,
                public_key=Keypair.random().public_key,
                client=FakeChainClient(),
            )


@pytest.mark.skipif(
    not os.getenv("STERISH_REGISTRY_CONTRACT_ID"),
    reason="live testnet contract not configured (STERISH-9 / STE-13 not deployed)",
)
class TestLiveTestnet:
    """Real on-chain flow. Runs only once a contract is deployed and configured.

    Set STERISH_REGISTRY_CONTRACT_ID, STERISH_AUDITOR_SECRET (and optionally
    STERISH_ESCROW_CONTRACT_ID) to exercise register -> verdict against testnet.
    """

    def test_submit_and_read_back(self) -> None:
        from sterish_pipeline.onchain import (
            SorobanChainClient,
            query_skill_from_chain,
        )

        contract_id = os.environ["STERISH_REGISTRY_CONTRACT_ID"]
        secret = os.environ["STERISH_AUDITOR_SECRET"]
        client = SorobanChainClient()
        orch = VerdictOrchestrator(
            client=client,
            registry_contract_id=contract_id,
            escrow_contract_id=os.getenv("STERISH_ESCROW_CONTRACT_ID", ""),
            auditor=Keypair.from_secret(secret),
        )
        result = orch.submit_audit(
            skill_id="com.sterish.livetest",
            version="1.0.0",
            verdict=FinalVerdict.SAFE,
            score=91,
            evidence_hash=E_HASH,
            content_hash=A_HASH,
        )
        assert result.verdict_tx
        assert query_skill_from_chain(contract_id, "com.sterish.livetest") is not None
