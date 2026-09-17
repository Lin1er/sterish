"""The paid path, with the chain, the facilitator and the mint stubbed. No network.

Organised around the rule STE-42 enforces: never take money for something that
cannot be handed over, and never take it twice. Each test that can move money
asserts how many times settle ran, not only what status came back.
"""

import base64
import json
import threading
import time

import pytest
from stellar_sdk import Keypair

from sterish_api import chain, payments, x402
from sterish_api.config import settings
from sterish_api.routes import use as use_route

SAFE = {
    "skill_id": "com.acme.pdf-suite",
    "version": "1.0.0",
    "content_hash": "a" * 64,
    "verdict": "SAFE",
    "trust_score": 88,
    "is_verified": True,
    "owner": "G" + "A" * 55,
    "auditor": "G" + "B" * 55,
    "registered_at": 1,
    "audited_at": 2,
    "evidence_hash": "b" * 64,
}
DANGEROUS = dict(SAFE, verdict="DANGEROUS", is_verified=False)
URL = f"/use/{SAFE['skill_id']}/1.0.0"

# Two real ed25519 accounts: the buyer, and someone else entirely. Both have keys, so
# the ownership proofs STE-48 requires can be signed for real rather than stubbed.
PAYER_KP = Keypair.from_raw_ed25519_seed(bytes([1]) * 32)
OTHER_KP = Keypair.from_raw_ed25519_seed(bytes([2]) * 32)
PAYER = PAYER_KP.public_key
OTHER = OTHER_KP.public_key
SETTLE_TX = "5" * 64
MINT_TX = "6" * 64


def _sep53_sign(keypair: Keypair, message: str) -> str:
    """What a wallet's signMessage and `stellar message sign` produce (SEP-53)."""
    import hashlib

    digest = hashlib.sha256(b"Stellar Signed Message:\n" + message.encode()).digest()
    return base64.b64encode(keypair.sign(digest)).decode()


def _proof(client, signer: Keypair = None, agent: str = PAYER, url: str = URL) -> dict:
    """Ask for a challenge as `agent`, sign it with `signer`, return the request headers."""
    signer = signer or PAYER_KP
    challenge = client.get(f"{url}/challenge", params={"agent": agent}).json()
    return {
        "X-AGENT-ADDRESS": agent,
        "X-STERISH-PROOF-NONCE": challenge["nonce"],
        "X-STERISH-PROOF-SIGNATURE": _sep53_sign(signer, challenge["message"]),
    }


def _payment_header(payload: dict | None = None) -> str:
    return base64.b64encode(json.dumps(payload or {"payload": {}}).encode()).decode()


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    """A skill on disk whose bytes hash to what the chain says."""
    from sterish_pipeline.content_hash import content_hash

    root = tmp_path / "artifacts" / SAFE["skill_id"] / SAFE["version"]
    root.mkdir(parents=True)
    (root / "manifest.json").write_bytes(b'{"skill_id":"com.acme.pdf-suite"}\n')
    digest = content_hash({"manifest.json": (root / "manifest.json").read_bytes()})
    previous = settings.skills_dir
    object.__setattr__(settings, "skills_dir", str(tmp_path / "artifacts"))
    monkeypatch.setattr(chain, "get_version", lambda s, v: dict(SAFE, content_hash=digest))
    yield digest
    object.__setattr__(settings, "skills_dir", previous)


@pytest.fixture
def no_artifact(tmp_path, monkeypatch):
    """A SAFE version with an artifact directory configured but nothing in it for us."""
    (tmp_path / "artifacts").mkdir()
    previous = settings.skills_dir
    object.__setattr__(settings, "skills_dir", str(tmp_path / "artifacts"))
    monkeypatch.setattr(chain, "get_version", lambda s, v: SAFE)
    yield
    object.__setattr__(settings, "skills_dir", previous)


class Ledger:
    """Stand-in for the chain's licence state plus the facilitator and the minter.

    Every money-moving call is counted, so a test can say "settled exactly once".
    """

    def __init__(self, monkeypatch, *, payer=PAYER):
        self.licences: set[tuple[str, str, str]] = set()
        self.settles = 0
        self.verifies = 0
        self.mints: list[str] = []
        self.payer = payer
        self.mint_error: Exception | None = None
        self.settle_delay = 0.0
        monkeypatch.setattr(chain, "has_license", self.has_license)
        monkeypatch.setattr(x402, "verify", self.verify)
        monkeypatch.setattr(x402, "settle", self.settle)
        monkeypatch.setattr(use_route, "_mint_license", self.mint)

    def has_license(self, agent, skill_id, version):
        return (agent, skill_id, version) in self.licences

    def verify(self, payment, requirements):
        self.verifies += 1
        return {"isValid": True, "payer": self.payer}

    def settle(self, payment, requirements):
        if self.settle_delay:
            time.sleep(self.settle_delay)
        self.settles += 1
        return {
            "success": True,
            "transaction": SETTLE_TX,
            "network": "stellar:testnet",
            "payer": self.payer,
        }

    def mint(self, agent, skill_id, version):
        if self.mint_error is not None:
            raise self.mint_error
        self.mints.append(agent)
        self.licences.add((agent, skill_id, version))
        return MINT_TX


# --- never offered -----------------------------------------------------------


def test_a_dangerous_version_can_never_be_sold(client, monkeypatch):
    """The claim the whole product rests on, at the point money changes hands."""
    monkeypatch.setattr(chain, "get_version", lambda s, v: DANGEROUS)
    r = client.get(URL)
    assert r.status_code == 403
    assert r.json()["error"] == "NOT_VERIFIED"
    assert "PAYMENT-REQUIRED" not in r.headers


class TestNothingUndeliverableIsPriced:
    """STE-42: the artifact used to be read only after settle and mint."""

    def test_no_artifact_is_404_with_no_payment_challenge(self, client, no_artifact):
        r = client.get(URL)
        assert r.status_code == 404
        assert r.json()["error"] == "ARTIFACT_NOT_FOUND"
        assert "PAYMENT-REQUIRED" not in r.headers

    def test_no_artifact_never_reaches_the_facilitator_even_with_a_payment(
        self, client, monkeypatch, no_artifact
    ):
        """The exact failure from the audit: paid, minted, then 404."""
        ledger = Ledger(monkeypatch)
        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.status_code == 404
        assert (ledger.verifies, ledger.settles, ledger.mints) == (0, 0, [])

    def test_hash_mismatch_is_500_before_any_challenge(self, client, monkeypatch, artifact):
        monkeypatch.setattr(chain, "get_version", lambda s, v: dict(SAFE, content_hash="f" * 64))
        r = client.get(URL)
        assert r.status_code == 500
        assert r.json()["error"] == "ARTIFACT_HASH_MISMATCH"
        assert "PAYMENT-REQUIRED" not in r.headers

    def test_hash_mismatch_never_settles(self, client, monkeypatch, artifact):
        """A buyer must not pay for one artifact and receive another — or nothing."""
        ledger = Ledger(monkeypatch)
        monkeypatch.setattr(chain, "get_version", lambda s, v: dict(SAFE, content_hash="f" * 64))
        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.status_code == 500
        assert (ledger.verifies, ledger.settles) == (0, 0)

    def test_hash_mismatch_is_never_served_to_a_licence_holder(self, client, monkeypatch, artifact):
        ledger = Ledger(monkeypatch)
        ledger.licences.add((PAYER, SAFE["skill_id"], "1.0.0"))
        monkeypatch.setattr(chain, "get_version", lambda s, v: dict(SAFE, content_hash="f" * 64))
        r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER})
        assert r.status_code == 500

    def test_unconfigured_artifact_dir_is_503_not_402(self, client, monkeypatch):
        monkeypatch.setattr(chain, "get_version", lambda s, v: SAFE)
        previous = settings.skills_dir
        object.__setattr__(settings, "skills_dir", "")
        try:
            r = client.get(URL)
        finally:
            object.__setattr__(settings, "skills_dir", previous)
        assert r.status_code == 503
        assert "PAYMENT-REQUIRED" not in r.headers

    def test_an_empty_artifact_directory_is_not_for_sale(self, client, monkeypatch, tmp_path):
        (tmp_path / "artifacts" / SAFE["skill_id"] / "1.0.0").mkdir(parents=True)
        previous = settings.skills_dir
        object.__setattr__(settings, "skills_dir", str(tmp_path / "artifacts"))
        monkeypatch.setattr(chain, "get_version", lambda s, v: SAFE)
        try:
            r = client.get(URL)
        finally:
            object.__setattr__(settings, "skills_dir", previous)
        assert r.status_code == 404
        assert "PAYMENT-REQUIRED" not in r.headers

    def test_a_path_segment_cannot_walk_out_of_the_artifact_dir(self, tmp_path):
        """skill_id and version come from the URL; `..` must not read elsewhere."""
        from sterish_api.errors import ApiError

        (tmp_path / "artifacts").mkdir()
        (tmp_path / "secret").mkdir()
        (tmp_path / "secret" / "key.txt").write_text("not for sale")
        previous = settings.skills_dir
        object.__setattr__(settings, "skills_dir", str(tmp_path / "artifacts"))
        try:
            for skill_id, version in (("..", "secret"), ("x", ".."), ("..", "..")):
                with pytest.raises(ApiError) as exc:
                    use_route._skill_bytes(skill_id, version, "a" * 64)
                assert exc.value.status == 404
        finally:
            object.__setattr__(settings, "skills_dir", previous)


# --- the challenge ------------------------------------------------------------


def test_unpaid_request_gets_a_402_challenge(client, artifact):
    r = client.get(URL)
    assert r.status_code == 402

    required = json.loads(base64.b64decode(r.headers["PAYMENT-REQUIRED"]))
    assert required["x402Version"] == 2
    accepts = required["accepts"][0]
    assert accepts["scheme"] == "exact"
    assert accepts["network"] == "stellar:testnet"
    assert accepts["amount"] == str(settings.price_base_units)
    assert r.headers["Cache-Control"] == "no-store"


def test_payto_is_a_classic_account_and_asset_is_the_sac(client, artifact):
    """Swapping these two is the documented common stumble, so it is pinned."""
    r = client.get(URL)
    accepts = json.loads(base64.b64decode(r.headers["PAYMENT-REQUIRED"]))["accepts"][0]
    assert accepts["payTo"].startswith("G")
    assert accepts["asset"].startswith("C")


def test_an_unlicensed_agent_hint_still_gets_the_challenge(client, monkeypatch, artifact):
    Ledger(monkeypatch)
    r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER})
    assert r.status_code == 402


def test_a_malformed_agent_hint_is_400_not_500(client, monkeypatch, artifact):
    Ledger(monkeypatch)
    r = client.get(URL, headers={"X-AGENT-ADDRESS": "not-an-address"})
    assert r.status_code == 400
    assert r.json()["error"] == "INVALID_AGENT"


def test_a_contract_address_is_not_an_agent(client, monkeypatch, artifact):
    Ledger(monkeypatch)
    r = client.get(URL, params={"agent": settings.usdc_sac})
    assert r.status_code == 400


# --- licence holders -----------------------------------------------------------


def test_an_existing_licence_is_served_without_payment(client, monkeypatch, artifact):
    ledger = Ledger(monkeypatch)
    ledger.licences.add((PAYER, SAFE["skill_id"], "1.0.0"))
    r = client.get(URL, headers=_proof(client))
    assert r.status_code == 200
    assert r.headers["X-STERISH-LICENSE"] == "held"
    assert json.loads(r.content) == {"manifest.json": '{"skill_id":"com.acme.pdf-suite"}\n'}
    assert ledger.verifies == ledger.settles == 0


def test_a_failed_licence_read_is_never_a_402(client, monkeypatch, artifact):
    """402 used to mean either "no licence" or "could not tell" (STE-35 finding)."""

    def broken(*a):
        raise chain.ContractError(6, "InvalidInput")

    monkeypatch.setattr(chain, "has_license", broken)
    r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER})
    assert r.status_code == 502
    assert r.json()["error"] == "LICENSE_READ_FAILED"
    assert "PAYMENT-REQUIRED" not in r.headers


def test_an_unreachable_rpc_on_the_licence_read_is_502(client, monkeypatch, artifact):
    def down(*a):
        raise chain.ChainError("timeout")

    monkeypatch.setattr(chain, "has_license", down)
    r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER})
    assert r.status_code == 502


# --- paying ----------------------------------------------------------------------


class TestPaying:
    def test_the_happy_path_settles_once_and_mints_to_the_payer(
        self, client, monkeypatch, artifact
    ):
        ledger = Ledger(monkeypatch)
        r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER, "X-PAYMENT": _payment_header()})
        assert r.status_code == 200
        assert r.headers["X-STERISH-LICENSE"] == "minted"
        assert r.headers["X-STERISH-LICENSE-TX"] == MINT_TX
        assert r.headers["X-STERISH-SETTLEMENT-TX"] == SETTLE_TX
        receipt = json.loads(base64.b64decode(r.headers["X-PAYMENT-RESPONSE"]))
        assert receipt["transaction"] == SETTLE_TX
        assert ledger.settles == 1
        assert ledger.mints == [PAYER]
        row = payments.get(SETTLE_TX)
        assert row["payer"] == PAYER and row["mint_tx"] == MINT_TX and row["minted_at"]

    def test_no_agent_header_still_mints_to_whoever_paid(self, client, monkeypatch, artifact):
        """Before STE-42 this settled the payment and then answered 400 UNKNOWN_PAYER:
        the Stellar exact payload has no payer field, so the header was the only
        source, and without it the money moved and no licence existed."""
        ledger = Ledger(monkeypatch)
        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.status_code == 200
        assert ledger.mints == [PAYER]

    def test_the_header_cannot_redirect_a_licence_to_someone_else(
        self, client, monkeypatch, artifact
    ):
        ledger = Ledger(monkeypatch)
        r = client.get(URL, headers={"X-AGENT-ADDRESS": OTHER, "X-PAYMENT": _payment_header()})
        assert r.status_code == 200
        assert ledger.mints == [PAYER]
        assert (OTHER, SAFE["skill_id"], "1.0.0") not in ledger.licences

    def test_a_payer_payload_field_is_ignored_in_favour_of_verify(
        self, client, monkeypatch, artifact
    ):
        ledger = Ledger(monkeypatch)
        header = _payment_header({"payload": {"payer": OTHER}, "payer": OTHER})
        client.get(URL, headers={"X-PAYMENT": header})
        assert ledger.mints == [PAYER]

    def test_a_payer_who_already_holds_the_licence_is_not_charged_again(
        self, client, monkeypatch, artifact
    ):
        """They sent a payment without the agent hint; verify names them, and they
        already hold it. Settling would take money for nothing."""
        ledger = Ledger(monkeypatch)
        ledger.licences.add((PAYER, SAFE["skill_id"], "1.0.0"))
        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.status_code == 200
        assert r.headers["X-STERISH-LICENSE"] == "held"
        assert ledger.settles == 0

    def test_a_second_purchase_after_success_is_served_held(self, client, monkeypatch, artifact):
        ledger = Ledger(monkeypatch)
        client.get(URL, headers={"X-PAYMENT": _payment_header()})
        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.headers["X-STERISH-LICENSE"] == "held"
        assert ledger.settles == 1

    def test_verify_without_a_payer_refuses_before_settling(self, client, monkeypatch, artifact):
        ledger = Ledger(monkeypatch, payer=None)
        r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER, "X-PAYMENT": _payment_header()})
        assert r.status_code == 502
        assert r.json()["error"] == "FACILITATOR_BAD_RESPONSE"
        assert ledger.settles == 0

    def test_verify_naming_a_contract_as_payer_refuses_before_settling(
        self, client, monkeypatch, artifact
    ):
        ledger = Ledger(monkeypatch, payer=settings.usdc_sac)
        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.status_code == 502
        assert ledger.settles == 0

    def test_settle_success_without_a_transaction_is_not_a_receipt(
        self, client, monkeypatch, artifact
    ):
        ledger = Ledger(monkeypatch)
        monkeypatch.setattr(x402, "settle", lambda *a: {"success": True, "transaction": ""})
        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.status_code == 502
        assert r.json()["error"] == "FACILITATOR_BAD_RESPONSE"
        assert ledger.mints == []

    def test_a_rejected_payment_is_402_with_the_facilitator_reason(
        self, client, monkeypatch, artifact
    ):
        ledger = Ledger(monkeypatch)

        def reject(*a, **k):
            raise x402.PaymentInvalid("insufficient_funds")

        monkeypatch.setattr(x402, "verify", reject)
        r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER, "X-PAYMENT": _payment_header()})
        assert r.status_code == 402
        assert r.json()["detail"] == "insufficient_funds"
        assert ledger.settles == 0

    def test_a_settlement_failure_is_402_and_mints_nothing(self, client, monkeypatch, artifact):
        ledger = Ledger(monkeypatch)

        def fail(*a, **k):
            raise x402.PaymentInvalid("settle_exact_stellar_transaction_failed")

        monkeypatch.setattr(x402, "settle", fail)
        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.status_code == 402
        assert ledger.mints == []
        assert payments.owed(PAYER, SAFE["skill_id"], "1.0.0") is None

    @pytest.mark.parametrize("stage", ["verify", "settle"])
    def test_a_facilitator_outage_is_not_reported_as_non_payment(
        self, client, monkeypatch, artifact, stage
    ):
        """503, not 402. Telling a buyer who just paid that they did not would invite
        them to pay twice."""
        ledger = Ledger(monkeypatch)

        def down(*a, **k):
            raise x402.FacilitatorError("connection refused")

        monkeypatch.setattr(x402, stage, down)
        r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER, "X-PAYMENT": _payment_header()})
        assert r.status_code == 503
        assert r.json()["error"] == "FACILITATOR_UNAVAILABLE"
        assert ledger.mints == []

    def test_a_malformed_payment_header_is_400(self, client, monkeypatch, artifact):
        ledger = Ledger(monkeypatch)
        r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER, "X-PAYMENT": "not-base64-json"})
        assert r.status_code == 400
        assert r.json()["error"] == "INVALID_PAYMENT"
        assert ledger.verifies == 0

    def test_concurrent_payments_from_one_payer_settle_once(self, client, monkeypatch, artifact):
        """Two tabs, two signed payments, one licence. Without the purchase lock both
        requests saw "no licence" and both settled."""
        ledger = Ledger(monkeypatch)
        ledger.settle_delay = 0.3
        results: list[int] = []

        def buy():
            results.append(client.get(URL, headers={"X-PAYMENT": _payment_header()}).status_code)

        threads = [threading.Thread(target=buy) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results == [200, 200, 200, 200]
        assert ledger.settles == 1
        assert ledger.mints == [PAYER]


# --- a mint that fails after the money moved ----------------------------------------


class TestMintAfterSettlement:
    def _pay_with_failing_mint(self, client, ledger, error):
        ledger.mint_error = error
        return client.get(URL, headers={"X-PAYMENT": _payment_header()})

    def test_mint_failure_is_502_naming_the_settlement(self, client, monkeypatch, artifact):
        from sterish_pipeline.onchain import OnChainError

        ledger = Ledger(monkeypatch)
        r = self._pay_with_failing_mint(client, ledger, OnChainError("did not finalise"))
        assert r.status_code == 502
        body = r.json()
        assert body["error"] == "LICENSE_MINT_PENDING"
        assert body["settlement_tx"] == SETTLE_TX
        assert body["settlement_tx_url"].endswith(SETTLE_TX)
        owed = payments.owed(PAYER, SAFE["skill_id"], "1.0.0")
        assert owed and owed["settle_tx"] == SETTLE_TX and "did not finalise" in owed["last_error"]

    def test_the_next_request_finishes_the_mint_without_charging(
        self, client, monkeypatch, artifact
    ):
        from sterish_pipeline.onchain import OnChainError

        ledger = Ledger(monkeypatch)
        self._pay_with_failing_mint(client, ledger, OnChainError("rpc timeout"))
        ledger.mint_error = None

        r = client.get(URL, headers=_proof(client))
        assert r.status_code == 200
        assert r.headers["X-STERISH-LICENSE"] == "minted"
        assert r.headers["X-STERISH-SETTLEMENT-TX"] == SETTLE_TX
        assert ledger.settles == 1
        assert ledger.mints == [PAYER]
        assert payments.owed(PAYER, SAFE["skill_id"], "1.0.0") is None

    def test_paying_again_while_owed_is_not_charged(self, client, monkeypatch, artifact):
        """A buyer who did not read the 502 and signs a fresh payment."""
        from sterish_pipeline.onchain import OnChainError

        ledger = Ledger(monkeypatch)
        self._pay_with_failing_mint(client, ledger, OnChainError("rpc timeout"))
        ledger.mint_error = None

        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.status_code == 200
        assert ledger.settles == 1

    def test_a_mint_that_actually_landed_is_not_minted_twice(self, client, monkeypatch, artifact):
        """The confirmation timed out, but the transaction made it on chain."""
        from sterish_pipeline.onchain import OnChainError

        ledger = Ledger(monkeypatch)
        self._pay_with_failing_mint(client, ledger, OnChainError("did not finalise"))
        ledger.licences.add((PAYER, SAFE["skill_id"], "1.0.0"))  # it landed after all
        ledger.mint_error = AssertionError("must not mint again")

        r = client.get(URL, headers=_proof(client))
        assert r.status_code == 200
        assert r.headers["X-STERISH-LICENSE"] == "held"
        assert payments.owed(PAYER, SAFE["skill_id"], "1.0.0") is None

    def test_already_minted_from_the_contract_closes_the_debt(self, client, monkeypatch, artifact):
        from sterish_pipeline.onchain import ContractCallError, OnChainError

        ledger = Ledger(monkeypatch)
        self._pay_with_failing_mint(client, ledger, OnChainError("did not finalise"))
        ledger.mint_error = ContractCallError(3, "mint_license", contract="tokens")

        r = client.get(URL, headers=_proof(client))
        assert r.status_code == 200
        assert r.headers["X-STERISH-SETTLEMENT-TX"] == SETTLE_TX
        assert payments.owed(PAYER, SAFE["skill_id"], "1.0.0") is None

    def test_a_contract_refusal_keeps_the_debt_open(self, client, monkeypatch, artifact):
        """E.g. NotSafeVerdict: the verdict flipped between settle and mint. The debt
        must stay recorded — it is owed a refund or a licence, not silence."""
        from sterish_pipeline.onchain import ContractCallError

        ledger = Ledger(monkeypatch)
        r = self._pay_with_failing_mint(
            client, ledger, ContractCallError(4, "mint_license", contract="tokens")
        )
        assert r.status_code == 502
        assert r.json()["error"] == "LICENSE_MINT_PENDING"
        assert payments.owed(PAYER, SAFE["skill_id"], "1.0.0") is not None

    def test_a_missing_minter_after_settlement_is_still_recorded(
        self, client, monkeypatch, artifact
    ):
        from sterish_api.errors import ApiError

        ledger = Ledger(monkeypatch)
        r = self._pay_with_failing_mint(
            client, ledger, ApiError(503, "NOT_CONFIGURED", "MINTER_SECRET is not set")
        )
        assert r.status_code == 503
        assert payments.get(SETTLE_TX) is not None

    def test_a_ledger_write_failure_does_not_stop_delivery(self, client, monkeypatch, artifact):
        ledger = Ledger(monkeypatch)

        def broken(*a, **k):
            raise RuntimeError("disk full")

        monkeypatch.setattr(payments, "record_settlement", broken)
        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.status_code == 200
        assert ledger.mints == [PAYER]


class TestHeaderCodec:
    def test_round_trip(self):
        payload = {"x402Version": 2, "accepts": [{"scheme": "exact"}]}
        assert x402.decode_header(x402.encode_header(payload)) == payload

    def test_garbage_raises_rather_than_returning_empty(self):
        with pytest.raises(ValueError):
            x402.decode_header("!!!not base64!!!")


def test_settlement_header_is_readable_by_a_browser(client, artifact):
    r = client.get(URL, headers={"Origin": "https://dashboard.example"})
    exposed = r.headers.get("access-control-expose-headers", "")
    assert "X-STERISH-SETTLEMENT-TX" in exposed
    assert "PAYMENT-REQUIRED" in exposed


# --- STE-48: a licence cannot be borrowed by naming its holder ------------------------


class TestOwnershipProof:
    """Licence holders are public on chain, so an address alone must never be enough."""

    @pytest.fixture
    def held(self, monkeypatch, artifact):
        ledger = Ledger(monkeypatch)
        ledger.licences.add((PAYER, SAFE["skill_id"], "1.0.0"))
        return ledger

    def test_naming_a_holder_without_proof_is_401_not_the_artifact(self, client, held):
        """The finding: anyone sending the holder's address received the bytes."""
        r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER})
        assert r.status_code == 401
        body = r.json()
        assert body["error"] == "OWNERSHIP_PROOF_REQUIRED"
        assert body["challenge_url"].endswith(f"{URL}/challenge?agent={PAYER}")
        assert body["signature_scheme"] == "SEP-53"
        assert "manifest.json" not in r.text
        assert "PAYMENT-REQUIRED" not in r.headers  # never 402: this caller may have paid
        assert held.verifies == held.settles == 0

    def test_the_query_parameter_form_is_refused_the_same_way(self, client, held):
        r = client.get(URL, params={"agent": PAYER})
        assert r.status_code == 401
        assert r.json()["error"] == "OWNERSHIP_PROOF_REQUIRED"

    def test_a_nonce_without_a_signature_is_still_proof_required(self, client, held):
        headers = _proof(client)
        del headers["X-STERISH-PROOF-SIGNATURE"]
        assert client.get(URL, headers=headers).json()["error"] == "OWNERSHIP_PROOF_REQUIRED"

    def test_a_valid_proof_serves_the_artifact(self, client, held):
        r = client.get(URL, headers=_proof(client))
        assert r.status_code == 200
        assert r.headers["X-STERISH-LICENSE"] == "held"
        assert held.settles == 0

    def test_a_signature_from_another_key_is_refused(self, client, held):
        """The attacker controls a key, just not the holder's."""
        r = client.get(URL, headers=_proof(client, signer=OTHER_KP, agent=PAYER))
        assert r.status_code == 401
        assert r.json()["error"] == "INVALID_OWNERSHIP_PROOF"
        assert "does not verify" in r.json()["detail"]
        assert "manifest.json" not in r.text

    def test_a_proof_cannot_be_replayed(self, client, held):
        headers = _proof(client)
        assert client.get(URL, headers=headers).status_code == 200
        again = client.get(URL, headers=headers)
        assert again.status_code == 401
        assert again.json()["error"] == "INVALID_OWNERSHIP_PROOF"
        assert "already been used" in again.json()["detail"]

    def test_an_expired_challenge_is_refused(self, client, held, monkeypatch):
        from sterish_api import proofs

        headers = _proof(client)
        real_time = time.time
        later = real_time() + settings.proof_ttl_seconds + 5
        monkeypatch.setattr(proofs.time, "time", lambda: later)
        r = client.get(URL, headers=headers)
        assert r.status_code == 401
        assert "expired" in r.json()["detail"]

    def test_a_failed_signature_does_not_burn_the_holders_nonce(self, client, held):
        headers = _proof(client)
        forged = dict(headers, **{"X-STERISH-PROOF-SIGNATURE": _sep53_sign(OTHER_KP, "anything")})
        assert client.get(URL, headers=forged).status_code == 401
        assert client.get(URL, headers=headers).status_code == 200

    def test_a_challenge_for_another_agent_cannot_be_reused(self, client, held):
        """OTHER asks for its own challenge and signs it correctly, then claims PAYER."""
        own = _proof(client, signer=OTHER_KP, agent=OTHER)
        stolen = dict(own, **{"X-AGENT-ADDRESS": PAYER})
        r = client.get(URL, headers=stolen)
        assert r.status_code == 401
        assert "different agent" in r.json()["detail"]

    def test_a_challenge_for_another_version_cannot_be_reused(self, client, held):
        headers = _proof(client, url=f"/use/{SAFE['skill_id']}/2.0.0")
        r = client.get(URL, headers=headers)
        assert r.status_code == 401
        assert "different skill or version" in r.json()["detail"]

    def test_the_signed_message_is_rebuilt_server_side(self, client, held):
        """Signing some other text containing the same nonce proves nothing."""
        challenge = client.get(f"{URL}/challenge", params={"agent": PAYER}).json()
        tampered = challenge["message"].replace("version: 1.0.0", "version: 9.9.9")
        headers = {
            "X-AGENT-ADDRESS": PAYER,
            "X-STERISH-PROOF-NONCE": challenge["nonce"],
            "X-STERISH-PROOF-SIGNATURE": _sep53_sign(PAYER_KP, tampered),
        }
        assert client.get(URL, headers=headers).status_code == 401

    def test_a_raw_ed25519_signature_without_the_sep53_prefix_is_refused(self, client, held):
        """One format, locked: a signature over the bare message is not SEP-53."""
        challenge = client.get(f"{URL}/challenge", params={"agent": PAYER}).json()
        raw = base64.b64encode(PAYER_KP.sign(challenge["message"].encode())).decode()
        headers = {
            "X-AGENT-ADDRESS": PAYER,
            "X-STERISH-PROOF-NONCE": challenge["nonce"],
            "X-STERISH-PROOF-SIGNATURE": raw,
        }
        assert client.get(URL, headers=headers).status_code == 401

    @pytest.mark.parametrize("bad", ["not base64!!", base64.b64encode(b"short").decode()])
    def test_a_malformed_signature_is_401_not_500(self, client, held, bad):
        headers = dict(_proof(client), **{"X-STERISH-PROOF-SIGNATURE": bad})
        r = client.get(URL, headers=headers)
        assert r.status_code == 401
        assert r.json()["error"] == "INVALID_OWNERSHIP_PROOF"

    def test_an_unknown_nonce_is_refused(self, client, held):
        headers = dict(_proof(client), **{"X-STERISH-PROOF-NONCE": "0" * 32})
        assert "unknown nonce" in client.get(URL, headers=headers).json()["detail"]

    def test_an_owed_settlement_also_needs_proof(self, client, monkeypatch, artifact):
        """The owed path mints and serves bytes too; naming the payer must not do it."""
        ledger = Ledger(monkeypatch)
        payments.record_settlement(PAYER, SAFE["skill_id"], "1.0.0", SETTLE_TX, "1000000")
        r = client.get(URL, headers={"X-AGENT-ADDRESS": PAYER})
        assert r.status_code == 401
        assert ledger.mints == []
        assert payments.owed(PAYER, SAFE["skill_id"], "1.0.0") is not None

    def test_a_non_holder_still_gets_402_with_or_without_proof(self, client, monkeypatch, artifact):
        """Proof only matters when there is something to prove; a buyer is asked to pay."""
        Ledger(monkeypatch)
        assert client.get(URL, headers={"X-AGENT-ADDRESS": PAYER}).status_code == 402
        assert client.get(URL, headers=_proof(client)).status_code == 402

    def test_the_paid_path_needs_no_proof(self, client, monkeypatch, artifact):
        """The x402 payment is signed by the payer, and the payer comes from /verify."""
        ledger = Ledger(monkeypatch)
        r = client.get(URL, headers={"X-PAYMENT": _payment_header()})
        assert r.status_code == 200
        assert r.headers["X-STERISH-LICENSE"] == "minted"
        assert ledger.settles == 1


class TestChallengeEndpoint:
    def test_the_challenge_names_everything_it_binds(self, client):
        body = client.get(f"{URL}/challenge", params={"agent": PAYER}).json()
        assert body["agent"] == PAYER and body["skill_id"] == SAFE["skill_id"]
        assert body["version"] == "1.0.0"
        assert len(body["nonce"]) == 32
        assert body["signature_scheme"] == "SEP-53"
        lines = body["message"].split("\n")
        assert lines == [
            "Sterish licence ownership proof",
            f"agent: {PAYER}",
            f"skill: {SAFE['skill_id']}",
            "version: 1.0.0",
            f"nonce: {body['nonce']}",
            f"expires: {body['expires_at']}",
            "network: Test SDF Network ; September 2015",
        ]
        assert 0 < body["expires_at"] - time.time() <= settings.proof_ttl_seconds

    def test_every_challenge_is_a_fresh_nonce(self, client):
        a = client.get(f"{URL}/challenge", params={"agent": PAYER}).json()["nonce"]
        b = client.get(f"{URL}/challenge", params={"agent": PAYER}).json()["nonce"]
        assert a != b

    def test_the_challenge_is_never_cached(self, client):
        r = client.get(f"{URL}/challenge", params={"agent": PAYER})
        assert r.headers["Cache-Control"] == "no-store"

    def test_the_header_form_works(self, client):
        r = client.get(f"{URL}/challenge", headers={"X-AGENT-ADDRESS": PAYER})
        assert r.status_code == 200

    @pytest.mark.parametrize(
        "agent, code",
        [
            (None, "MISSING_AGENT"),
            ("not-an-address", "INVALID_AGENT"),
            ("CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T", "INVALID_AGENT"),
            (
                "MA7QYNF7SOWQ3GLR2BGMZEHXAVIRZA4KVWLTJJFC7MGXUA74P7UJUAAAAAAAAAAAAGZFQ",
                "INVALID_AGENT",
            ),
        ],
    )
    def test_the_agent_is_validated(self, client, agent, code):
        params = {"agent": agent} if agent else {}
        r = client.get(f"{URL}/challenge", params=params)
        assert r.status_code == 400
        assert r.json()["error"] == code

    def test_a_proof_signed_with_the_stellar_cli_format_verifies(self):
        """Pin the digest to SEP-53 independently of our own signing helper."""
        import hashlib

        from sterish_api import proofs

        message = "hello"
        assert proofs.sep53_digest(message) == hashlib.sha256(
            b"Stellar Signed Message:\nhello"
        ).digest()


def test_a_signature_made_by_the_stellar_cli_verifies():
    """Known answer, captured from `stellar message sign "hello" --sign-with-key <seed 0x01*32>`
    (stellar-cli, 2026-09-17). The same bytes came out of demo/x402-buyer/prove.js. If this
    ever fails, the server and every real signer disagree about SEP-53."""
    from sterish_api import proofs

    signature = base64.b64decode(
        "u5X4XThfRD8os95F82YDnzd/ow2uGibbTlisjIHkxaoEfgI7K4QN/oz9K5Vm9dut9zcT8kUJydc2VqonO0cWAQ=="
    )
    PAYER_KP.verify(proofs.sep53_digest("hello"), signature)
