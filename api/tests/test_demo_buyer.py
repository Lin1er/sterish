"""The demo buyer (STE-43), offline.

The purchase runs through the real app over a TestClient — the same `/use` handler an
outside agent hits — with only the network edges stubbed: Horizon, the facilitator,
the mint, and the payment signer. The signer itself is tested separately below
against a fake RPC that returns real XDR.
"""

import json
import math
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from stellar_sdk import Address, Keypair, scval
from stellar_sdk import xdr as stellar_xdr
from stellar_sdk.base_soroban_server import _assemble_transaction

from sterish_api import chain, demo_buyer, x402, x402_client
from sterish_api.config import settings
from sterish_api.errors import ApiError
from sterish_api.routes import use as use_route

SKILL, VERSION = "com.acme.pdf-suite", "1.0.0"
SAFE = {
    "skill_id": SKILL,
    "version": VERSION,
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
TREASURY = Keypair.random()
USDC_ISSUER = settings.usdc_classic_issuer
SETTLE_TX, MINT_TX, FUND_TX = "5" * 64, "6" * 64, "7" * 64


def _set(**values):
    previous = {k: getattr(settings, k) for k in values}
    for k, v in values.items():
        object.__setattr__(settings, k, v)
    return previous


@pytest.fixture
def demo_on():
    previous = _set(
        demo_enabled=True,
        demo_treasury_secret=TREASURY.secret,
        demo_daily_limit=50,
        demo_per_client_per_hour=5,
    )
    yield
    _set(**previous)


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    from sterish_pipeline.content_hash import content_hash

    root = tmp_path / "artifacts" / SKILL / VERSION
    root.mkdir(parents=True)
    (root / "SKILL.md").write_bytes(b"# PDF suite\n")
    digest = content_hash({"SKILL.md": b"# PDF suite\n"})
    previous = _set(skills_dir=str(tmp_path / "artifacts"))
    monkeypatch.setattr(chain, "get_version", lambda s, v: dict(SAFE, content_hash=digest))
    yield digest
    _set(**previous)


class FakeHorizon:
    def __init__(self, usdc="3", xlm="100"):
        self.balances = [
            {"asset_type": "native", "balance": xlm},
            {
                "asset_type": "credit_alphanum4",
                "asset_code": "USDC",
                "asset_issuer": USDC_ISSUER,
                "balance": usdc,
            },
        ]
        self.submitted = []
        self.fail_submit = False

    def accounts(self):
        horizon = self

        class _Q:
            def account_id(self, _):
                return self

            def call(self):
                return {"balances": horizon.balances}

        return _Q()

    def load_account(self, account_id):
        from stellar_sdk import Account

        return Account(account_id, 1)

    def submit_transaction(self, tx):
        if self.fail_submit:
            raise RuntimeError("tx_bad_seq")
        self.submitted.append(tx)
        return {"hash": FUND_TX}


class ChainStub:
    """Licence state plus facilitator plus minter, for the /use the demo calls."""

    def __init__(self, monkeypatch):
        self.licences = set()
        self.settles = 0
        self.payer = None
        monkeypatch.setattr(chain, "has_license", lambda a, s, v: (a, s, v) in self.licences)
        monkeypatch.setattr(x402, "verify", self.verify)
        monkeypatch.setattr(x402, "settle", self.settle)
        monkeypatch.setattr(use_route, "_mint_license", self.mint)

    def verify(self, payment, requirements):
        return {"isValid": True, "payer": self.payer}

    def settle(self, payment, requirements):
        self.settles += 1
        return {"success": True, "transaction": SETTLE_TX, "payer": self.payer}

    def mint(self, agent, skill_id, version):
        self.licences.add((agent, skill_id, version))
        return MINT_TX


@pytest.fixture
def world(monkeypatch, demo_on, artifact):
    """A buyer wired to the real app, with the network edges stubbed."""
    from sterish_api.main import app

    stub = ChainStub(monkeypatch)
    horizon = FakeHorizon()

    def fake_build(required, signer, **kwargs):
        stub.payer = signer.public_key
        return {
            "x402Version": 2,
            "payload": {"transaction": "AAAA"},
            "accepted": required["accepts"][0],
        }

    monkeypatch.setattr(x402_client, "build_payment", fake_build)
    buyer = demo_buyer.DemoBuyer(http_factory=lambda: TestClient(app), horizon=horizon)
    monkeypatch.setattr(demo_buyer, "buyer", buyer)
    return SimpleNamespace(buyer=buyer, stub=stub, horizon=horizon, app=app)


def _run(world, client_id="1.2.3.4"):
    job = world.buyer.start(SKILL, VERSION, client_id)
    # start() already launched a thread; wait for it rather than racing it.
    for _ in range(200):
        if world.buyer.get(job.job_id).status in ("succeeded", "failed"):
            break
        threading.Event().wait(0.02)
    return world.buyer.get(job.job_id)


# --- refused before anything moves ----------------------------------------------------


def test_disabled_is_503_and_status_says_so(client):
    r = client.post("/demo/purchases", json={"skill_id": SKILL, "version": VERSION})
    assert r.status_code == 503
    assert r.json()["error"] == "DEMO_DISABLED"
    assert client.get("/demo/status").json()["enabled"] is False


def test_enabled_without_a_treasury_is_still_disabled(client):
    previous = _set(demo_enabled=True, demo_treasury_secret="")
    try:
        r = client.post("/demo/purchases", json={"skill_id": SKILL, "version": VERSION})
    finally:
        _set(**previous)
    assert r.status_code == 503


def test_a_dangerous_version_is_refused_before_a_job_exists(world, monkeypatch):
    monkeypatch.setattr(
        chain, "get_version", lambda s, v: dict(SAFE, verdict="DANGEROUS", is_verified=False)
    )
    with pytest.raises(ApiError) as exc:
        world.buyer.start(SKILL, VERSION, "c")
    assert exc.value.status == 403
    assert world.horizon.submitted == []
    assert world.buyer.status()["used_today"] == 0


def test_an_undeliverable_version_is_refused_before_a_job_exists(world, monkeypatch, tmp_path):
    previous = _set(skills_dir=str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    try:
        with pytest.raises(ApiError) as exc:
            world.buyer.start(SKILL, VERSION, "c")
    finally:
        _set(**previous)
    assert exc.value.status == 404 and exc.value.error == "ARTIFACT_NOT_FOUND"
    assert world.horizon.submitted == []


def test_an_unregistered_skill_is_a_404_from_the_chain(world, monkeypatch, client):
    def missing(s, v):
        raise chain.ContractError(3, "SkillNotFound")

    monkeypatch.setattr(chain, "get_version", missing)
    r = client.post("/demo/purchases", json={"skill_id": "com.nope", "version": "1.0.0"})
    assert r.status_code == 404
    assert r.json()["error"] == "SKILL_NOT_FOUND"


def test_one_purchase_at_a_time(world):
    world.buyer._running = "someone-else"
    with pytest.raises(ApiError) as exc:
        world.buyer.start(SKILL, VERSION, "c")
    assert exc.value.status == 409
    assert exc.value.extra == {"running_job_id": "someone-else"}


def test_per_client_hourly_limit(world, monkeypatch):
    now = [1_000_000.0]
    world.buyer._clock = lambda: now[0]
    _set(demo_per_client_per_hour=2)
    for _ in range(2):
        job = world.buyer.start(SKILL, VERSION, "same-client")
        world.buyer._running = None  # let the next one start; the thread still runs
        assert job.job_id
    with pytest.raises(ApiError) as exc:
        world.buyer.start(SKILL, VERSION, "same-client")
    assert exc.value.error == "DEMO_RATE_LIMITED"
    # Another client is unaffected; an hour later the first is free again.
    world.buyer.start(SKILL, VERSION, "other-client")
    world.buyer._running = None
    now[0] += 3601
    world.buyer.start(SKILL, VERSION, "same-client")


def test_daily_limit_and_rollover(world):
    now = [1_789_430_400.0]  # 2026-09-15T00:00:00Z
    world.buyer._clock = lambda: now[0]
    _set(demo_daily_limit=1, demo_per_client_per_hour=99)
    world.buyer.start(SKILL, VERSION, "a")
    world.buyer._running = None
    with pytest.raises(ApiError) as exc:
        world.buyer.start(SKILL, VERSION, "b")
    assert exc.value.error == "DEMO_DAILY_LIMIT"
    now[0] += 86400
    world.buyer.start(SKILL, VERSION, "b")


# --- the purchase ----------------------------------------------------------------------


def test_a_purchase_runs_every_step_through_the_real_use_path(world):
    job = _run(world)
    body = job.to_dict()

    assert job.status == "succeeded", body
    assert [s["status"] for s in body["steps"]] == ["ok"] * len(demo_buyer.STEPS)
    steps = {s["key"]: s for s in body["steps"]}
    assert steps["fund_agent"]["tx_hash"] == FUND_TX
    assert steps["challenge"]["data"]["status"] == 402
    assert steps["pay"]["data"]["settlement_tx"] == SETTLE_TX
    assert steps["pay"]["tx_hash"] == MINT_TX
    assert steps["repeat_free"]["data"]["licence"] == "held"
    assert world.stub.settles == 1
    assert (job.agent, SKILL, VERSION) in world.stub.licences

    assert body["signer"]["kind"] == "demo"
    assert body["signer"]["treasury"] == TREASURY.public_key
    assert "not by your wallet" in body["signer"]["notice"]


def test_the_agent_is_funded_with_exactly_the_price(world):
    job = _run(world)
    tx = world.horizon.submitted[0]
    ops = tx.transaction.operations
    assert [type(o).__name__ for o in ops] == ["CreateAccount", "ChangeTrust", "Payment"]
    assert ops[0].destination == job.agent
    assert ops[1].source.account_id == job.agent
    assert str(ops[2].amount) == "0.1"
    # Signed by both: the treasury pays, the agent consents to its trustline.
    assert len(tx.signatures) == 2


def test_no_secret_ever_appears_in_a_response(world, client):
    job = _run(world)
    rendered = json.dumps(job.to_dict()) + client.get("/demo/status").text
    assert TREASURY.secret not in rendered
    assert "SC" not in "".join(w for w in rendered.split('"') if len(w) == 56 and w.startswith("S"))


def test_treasury_too_low_fails_before_funding(world):
    world.horizon.balances[1]["balance"] = "0.05"
    job = _run(world)
    assert job.status == "failed"
    assert job.error["code"] == "TREASURY_LOW" and job.error["step"] == "fund_agent"
    assert world.horizon.submitted == []
    assert [s.status for s in job.steps[1:]] == ["skipped"] * (len(demo_buyer.STEPS) - 1)


def test_treasury_without_enough_xlm_fails_before_funding(world):
    world.horizon.balances[0]["balance"] = "2.5"
    job = _run(world)
    assert job.error["code"] == "TREASURY_LOW"
    assert world.horizon.submitted == []


def test_a_funding_failure_is_reported(world):
    world.horizon.fail_submit = True
    job = _run(world)
    assert job.error["code"] == "FUNDING_FAILED"


def test_a_rejected_payment_names_the_facilitator_reason(world, monkeypatch):
    def reject(*a):
        raise x402.PaymentInvalid("insufficient_funds")

    monkeypatch.setattr(x402, "verify", reject)
    job = _run(world)
    assert job.status == "failed"
    assert job.error["code"] == "PAYMENT_REJECTED" and job.error["step"] == "pay"
    assert "insufficient_funds" in job.error["detail"]
    assert world.stub.settles == 0


def test_a_facilitator_outage_is_reported_as_such(world, monkeypatch):
    def down(*a):
        raise x402.FacilitatorError("connection refused")

    monkeypatch.setattr(x402, "verify", down)
    job = _run(world)
    assert job.error["code"] == "FACILITATOR_UNAVAILABLE"


def test_a_payment_that_cannot_be_built_is_reported(world, monkeypatch):
    def cannot(*a, **k):
        raise x402_client.PaymentBuildError("simulation failed: HostError")

    monkeypatch.setattr(x402_client, "build_payment", cannot)
    job = _run(world)
    assert job.error == {
        "code": "PAYMENT_BUILD_FAILED",
        "detail": "simulation failed: HostError",
        "step": "sign_payment",
    }


def test_a_crash_ends_the_job_and_frees_the_lock(world, monkeypatch):
    def boom(*a, **k):
        raise KeyError("surprise")

    monkeypatch.setattr(x402_client, "build_payment", boom)
    job = _run(world)
    assert job.status == "failed" and job.error["code"] == "INTERNAL"
    assert job.finished_at
    assert world.buyer.status()["busy"] is False


def test_bytes_that_do_not_match_the_chain_fail_the_step(world):
    job = demo_buyer.Job(job_id="x", skill_id=SKILL, version=VERSION)
    step = demo_buyer.Step(key="verify_bytes", title="")
    ctx = {"served": json.dumps({"SKILL.md": "other"}).encode(), "record": dict(SAFE)}
    with pytest.raises(demo_buyer.DemoStepFailed) as exc:
        world.buyer._step_verify_bytes(job, step, ctx)
    assert exc.value.code == "BYTES_MISMATCH"


def test_a_repeat_that_is_not_free_fails_the_step(world, monkeypatch):
    agent = Keypair.random()
    job = demo_buyer.Job(job_id="x", skill_id=SKILL, version=VERSION)
    step = demo_buyer.Step(key="repeat_free", title="")
    with TestClient(world.app) as http:
        with pytest.raises(demo_buyer.DemoStepFailed) as exc:
            world.buyer._step_repeat_free(job, step, {"agent": agent, "http": http})
    assert exc.value.code == "REPEAT_NOT_FREE"


# --- the HTTP surface ---------------------------------------------------------------------


def test_post_returns_202_with_a_pollable_location(world, client):
    r = client.post(
        "/demo/purchases",
        json={"skill_id": SKILL, "version": VERSION},
        headers={"CF-Connecting-IP": "9.9.9.9"},
    )
    assert r.status_code == 202
    body = r.json()
    assert r.headers["Location"] == f"/demo/purchases/{body['job_id']}"
    assert body["signer"]["kind"] == "demo"
    for _ in range(200):
        polled = client.get(r.headers["Location"]).json()
        if polled["status"] in ("succeeded", "failed"):
            break
        threading.Event().wait(0.02)
    assert polled["status"] == "succeeded", polled


def test_unknown_job_is_404(client):
    r = client.get("/demo/purchases/nope")
    assert r.status_code == 404
    assert r.json()["error"] == "DEMO_JOB_NOT_FOUND"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"skill_id": "", "version": "1.0.0"},
        {"skill_id": "x"},
        {"skill_id": "x" * 201, "version": "1"},
    ],
)
def test_malformed_bodies_are_422(client, payload):
    assert client.post("/demo/purchases", json=payload).status_code == 422


def test_a_browser_may_post(client):
    r = client.options(
        "/demo/purchases",
        headers={"Origin": "https://dashboard.example", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 200
    assert "POST" in r.headers["access-control-allow-methods"]


def test_client_identity_prefers_the_proxy_headers():
    from starlette.requests import Request

    from sterish_api.routes.demo import client_id

    def req(headers):
        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("10.0.0.1", 1),
        }
        return Request(scope)

    assert (
        client_id(req({"CF-Connecting-IP": "1.1.1.1", "X-Forwarded-For": "2.2.2.2"})) == "1.1.1.1"
    )
    assert client_id(req({"X-Forwarded-For": "2.2.2.2, 3.3.3.3"})) == "2.2.2.2"
    assert client_id(req({})) == "10.0.0.1"


# --- the signer, against a fake RPC with real XDR -----------------------------------------------

PAY_TO = "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU"
ASSET = "CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA"


def _required(**overrides):
    offer = {
        "scheme": "exact",
        "network": "stellar:testnet",
        "amount": "1000000",
        "asset": ASSET,
        "payTo": PAY_TO,
        "maxTimeoutSeconds": 300,
        "extra": {"areFeesSponsored": True},
    }
    offer.update(overrides)
    return {"x402Version": 2, "resource": {"url": "https://x/use/a/1"}, "accepts": [offer]}


def _auth_entry(address: str, amount: int = 1_000_000) -> str:
    entry = stellar_xdr.SorobanAuthorizationEntry(
        credentials=stellar_xdr.SorobanCredentials(
            type=stellar_xdr.SorobanCredentialsType.SOROBAN_CREDENTIALS_ADDRESS,
            address=stellar_xdr.SorobanAddressCredentials(
                address=Address(address).to_xdr_sc_address(),
                nonce=stellar_xdr.Int64(42),
                signature_expiration_ledger=stellar_xdr.Uint32(0),
                signature=scval.to_void(),
            ),
        ),
        root_invocation=stellar_xdr.SorobanAuthorizedInvocation(
            function=stellar_xdr.SorobanAuthorizedFunction(
                type=stellar_xdr.SorobanAuthorizedFunctionType.SOROBAN_AUTHORIZED_FUNCTION_TYPE_CONTRACT_FN,
                contract_fn=stellar_xdr.InvokeContractArgs(
                    contract_address=Address(ASSET).to_xdr_sc_address(),
                    function_name=stellar_xdr.SCSymbol(b"transfer"),
                    args=[
                        scval.to_address(address),
                        scval.to_address(PAY_TO),
                        scval.to_int128(amount),
                    ],
                ),
            ),
            sub_invocations=[],
        ),
    )
    return entry.to_xdr()


def _soroban_data() -> str:
    resources = stellar_xdr.SorobanResources(
        footprint=stellar_xdr.LedgerFootprint(read_only=[], read_write=[]),
        instructions=stellar_xdr.Uint32(1000),
        disk_read_bytes=stellar_xdr.Uint32(0),
        write_bytes=stellar_xdr.Uint32(0),
    )
    data = stellar_xdr.SorobanTransactionData(
        ext=stellar_xdr.SorobanTransactionDataExt(0),
        resources=resources,
        resource_fee=stellar_xdr.Int64(5000),
    )
    return data.to_xdr()


class FakeRpc:
    def __init__(self, auth_address: str, ledger: int = 1000):
        self.auth_address = auth_address
        self.ledger = ledger
        self.simulated = []

    def get_latest_ledger(self):
        return SimpleNamespace(sequence=self.ledger)

    def simulate_transaction(self, tx, use_upgraded_auth=True):
        assert use_upgraded_auth is False
        self.simulated.append(tx)
        return SimpleNamespace(
            error=None,
            restore_preamble=None,
            results=[
                SimpleNamespace(auth=[_auth_entry(self.auth_address)], xdr=scval.to_void().to_xdr())
            ],
            transaction_data=_soroban_data(),
            min_resource_fee=5000,
        )

    def prepare_transaction(self, tx, sim):
        return _assemble_transaction(tx, sim)


def test_build_payment_signs_the_payers_entry_with_the_facilitator_expiry():
    agent = Keypair.random()
    rpc = FakeRpc(agent.public_key, ledger=1000)
    payment = x402_client.build_payment(
        _required(), agent, rpc_url="unused", horizon_url="unused", server=rpc, ledger_seconds=5
    )

    assert payment["x402Version"] == 2
    assert payment["accepted"]["payTo"] == PAY_TO
    assert payment["resource"] == {"url": "https://x/use/a/1"}

    from stellar_sdk import TransactionEnvelope

    envelope = TransactionEnvelope.from_xdr(
        payment["payload"]["transaction"], x402_client.NETWORK_PASSPHRASES["stellar:testnet"]
    )
    op = envelope.transaction.operations[0]
    assert len(op.auth) == 1
    creds = op.auth[0].credentials.address
    assert creds.signature.type != stellar_xdr.SCValType.SCV_VOID
    # ceil(maxTimeoutSeconds / ledger seconds) past the latest ledger — inside the
    # facilitator's ceiling of that plus 2.
    assert creds.signature_expiration_ledger.uint32 == 1000 + math.ceil(300 / 5)
    signed, pending = x402_client.signature_status(op.auth)
    assert signed == {agent.public_key} and pending == set()
    assert len(rpc.simulated) == 2  # re-simulated after signing


def test_build_payment_refuses_a_transfer_that_needs_someone_elses_signature():
    agent = Keypair.random()
    rpc = FakeRpc(Keypair.random().public_key)
    with pytest.raises(x402_client.PaymentBuildError, match="expected to sign with"):
        x402_client.build_payment(
            _required(), agent, rpc_url="u", horizon_url="u", server=rpc, ledger_seconds=5
        )


def test_build_payment_reports_a_simulation_error():
    agent = Keypair.random()
    rpc = FakeRpc(agent.public_key)
    rpc.simulate_transaction = lambda tx, use_upgraded_auth=True: SimpleNamespace(
        error="HostError: balance", restore_preamble=None, results=None
    )
    with pytest.raises(x402_client.PaymentBuildError, match="balance"):
        x402_client.build_payment(
            _required(), agent, rpc_url="u", horizon_url="u", server=rpc, ledger_seconds=5
        )


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"amount": "0"}, "positive integer"),
        ({"amount": "1.5"}, "positive integer"),
        ({"payTo": "nope"}, "invalid payTo"),
        ({"asset": PAY_TO}, "invalid asset"),
        ({"extra": {}}, "areFeesSponsored"),
        ({"network": "stellar:pubnet"}, "no exact offer"),
        ({"scheme": "upto"}, "no exact offer"),
    ],
)
def test_requirements_are_validated_like_the_js_client(overrides, message):
    with pytest.raises(x402_client.PaymentBuildError, match=message):
        x402_client.select_requirements(_required(**overrides), "stellar:testnet")


def test_wrong_x402_version_is_refused():
    with pytest.raises(x402_client.PaymentBuildError, match="x402Version"):
        x402_client.select_requirements(dict(_required(), x402Version=1), "stellar:testnet")


def test_ledger_seconds_estimate_and_its_fallback():
    import httpx

    def handler(request):
        records = [{"closed_at": f"2026-09-15T00:00:{50 - 5 * i:02d}Z"} for i in range(10)]
        return httpx.Response(200, json={"_embedded": {"records": records}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert x402_client.estimated_ledger_seconds("https://h", client=http) == 5

    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as http:
        assert x402_client.estimated_ledger_seconds("https://h", client=http) == 5
