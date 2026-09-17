"""A buyer service a dashboard can drive, signing with a demo account (STE-43).

STE-22 needs the x402 loop to run from the dashboard with no CLI, so a non-technical
reviewer can watch 402 -> pay USDC -> licence minted -> 200. The primary path there is
signing in the browser; the fallback STE-22 names is this: the dashboard asks the
backend to run the purchase with a server-side demo signer, and shows every
transaction it produced, labelled clearly as a demo account.

Deliberately NOT a shortcut. Each run creates a fresh agent account and then buys
through **the public `/use` endpoint over HTTP**, exactly as an outside agent would:
the same 402, the same facilitator verify and settle, the same mint, the same
content-pinned bytes. If this demo works, the real path works, and the other way
round.

Guard rails, because a public endpoint that spends money is a target:

* disabled unless `DEMO_BUYER_ENABLED=1` and a treasury secret is configured;
* a version that is not SAFE, or that `/use` cannot deliver, is refused
  synchronously, before any account is created or any USDC moves;
* one purchase at a time across the whole process;
* a per-client hourly limit and a process-wide daily limit;
* the treasury's balance is checked before an agent is funded.

Jobs live in memory. They are a progress view for the dashboard, not a record: the
record is the ledger, and every step that touched it carries its transaction hash.
"""

from __future__ import annotations

import base64
import collections
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from stellar_sdk import Asset, Keypair, Server, TransactionBuilder

from . import chain, proofs, x402, x402_client
from .config import settings
from .errors import ApiError

logger = logging.getLogger(__name__)

SAC_DECIMALS = Decimal(10) ** 7
MAX_JOBS_KEPT = 100
DEMO_NOTICE = (
    "This purchase is signed by a Sterish demo account on Stellar testnet, not by your "
    "wallet. Every step below is a real testnet transaction you can open on stellar.expert."
)

STEPS: list[tuple[str, str]] = [
    ("fund_agent", "A fresh agent account is created and funded by the demo treasury"),
    ("challenge", "The agent asks for the skill without paying and receives HTTP 402"),
    ("sign_payment", "The agent signs a USDC transfer authorization for exactly the price"),
    ("pay", "The agent retries with the payment: Sterish verifies, settles and mints the licence"),
    ("verify_bytes", "The bytes served hash to the content_hash recorded on chain"),
    ("licence_on_chain", "The tokens contract reports the licence as held"),
    ("repeat_free", "A second request is served from the licence, without paying again"),
]


class DemoStepFailed(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass
class Step:
    key: str
    title: str
    status: str = "pending"  # pending | running | ok | failed | skipped
    detail: str | None = None
    tx_hash: str | None = None
    tx_url: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None


@dataclass
class Job:
    job_id: str
    skill_id: str
    version: str
    status: str = "queued"  # queued | running | succeeded | failed
    agent: str | None = None
    error: dict[str, str] | None = None
    created_at: str = ""
    finished_at: str | None = None
    steps: list[Step] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        body = asdict(self)
        body["signer"] = {
            "kind": "demo",
            "treasury": _treasury_address(),
            "notice": DEMO_NOTICE,
        }
        body["network"] = settings.network
        return body


def _now() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _treasury_address() -> str | None:
    if not settings.demo_treasury_secret:
        return None
    try:
        return Keypair.from_secret(settings.demo_treasury_secret).public_key
    except Exception:  # noqa: BLE001 - a malformed secret is reported by status()
        return None


class DemoBuyer:
    """Runs demo purchases one at a time on a worker thread."""

    def __init__(
        self,
        http_factory: Callable[[], httpx.Client] | None = None,
        horizon: Server | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self._http_factory = http_factory or (
            lambda: httpx.Client(base_url=settings.demo_self_url, timeout=120)
        )
        self._horizon = horizon
        self._clock = clock
        self._lock = threading.Lock()
        self._jobs: collections.OrderedDict[str, Job] = collections.OrderedDict()
        self._running: str | None = None
        self._per_client: dict[str, collections.deque[float]] = collections.defaultdict(
            collections.deque
        )
        self._day: str = ""
        self._today = 0

    # --- public -------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._roll_day()
            return {
                "enabled": self._enabled(),
                "network": settings.network,
                "treasury": _treasury_address(),
                "busy": self._running is not None,
                "running_job_id": self._running,
                "daily_limit": settings.demo_daily_limit,
                "used_today": self._today,
                "per_client_hourly_limit": settings.demo_per_client_per_hour,
                "notice": DEMO_NOTICE,
            }

    def start(self, skill_id: str, version: str, client_id: str) -> Job:
        if not self._enabled():
            raise ApiError(
                503,
                "DEMO_DISABLED",
                "the demo buyer is disabled on this deployment (DEMO_BUYER_ENABLED)",
            )

        # Refuse before anything moves: same checks, same order, as /use itself.
        record = chain.get_version(skill_id, version)
        if not record["is_verified"]:
            raise ApiError(
                403,
                "NOT_VERIFIED",
                f"{skill_id}@{version} is {record['verdict']}; only SAFE versions are licensable",
            )
        from .routes.use import _skill_bytes

        _skill_bytes(skill_id, version, record["content_hash"])

        with self._lock:
            self._roll_day()
            if self._running is not None:
                raise ApiError(
                    409,
                    "DEMO_BUSY",
                    "a demo purchase is already running; poll it or try again shortly",
                    {"running_job_id": self._running},
                )
            window = self._per_client[client_id]
            cutoff = self._clock() - 3600
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) >= settings.demo_per_client_per_hour:
                raise ApiError(
                    429,
                    "DEMO_RATE_LIMITED",
                    f"at most {settings.demo_per_client_per_hour} demo purchases "
                    "per hour per client",
                )
            if self._today >= settings.demo_daily_limit:
                raise ApiError(
                    429,
                    "DEMO_DAILY_LIMIT",
                    f"the demo buyer has run its {settings.demo_daily_limit} purchases for today",
                )

            window.append(self._clock())
            self._today += 1
            job = Job(
                job_id=uuid.uuid4().hex,
                skill_id=skill_id,
                version=version,
                created_at=_now(),
                steps=[Step(key=k, title=t) for k, t in STEPS],
            )
            self._jobs[job.job_id] = job
            while len(self._jobs) > MAX_JOBS_KEPT:
                self._jobs.popitem(last=False)
            self._running = job.job_id

        thread = threading.Thread(
            target=self._run, args=(job, record), name=f"demo-{job.job_id[:8]}", daemon=True
        )
        thread.start()
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise ApiError(404, "DEMO_JOB_NOT_FOUND", f"no demo purchase {job_id!r}")
        return job

    def run_sync(self, job: Job, record: dict) -> None:
        """For tests: run a job on the calling thread."""
        self._run(job, record)

    # --- internals ------------------------------------------------------------------

    def _enabled(self) -> bool:
        return bool(settings.demo_enabled and settings.demo_treasury_secret)

    def _roll_day(self) -> None:
        day = datetime.fromtimestamp(self._clock(), tz=UTC).strftime("%Y-%m-%d")
        if day != self._day:
            self._day, self._today = day, 0

    def _horizon_server(self) -> Server:
        return self._horizon or Server(settings.horizon_url)

    def _run(self, job: Job, record: dict) -> None:
        job.status = "running"
        steps = {s.key: s for s in job.steps}
        ctx: dict[str, Any] = {"record": record}
        try:
            with self._http_factory() as http:
                ctx["http"] = http
                for key, _ in STEPS:
                    step = steps[key]
                    step.status, step.started_at = "running", _now()
                    getattr(self, f"_step_{key}")(job, step, ctx)
                    step.status, step.finished_at = "ok", _now()
            job.status = "succeeded"
        except DemoStepFailed as exc:
            self._fail(job, exc.code, exc.detail)
        except ApiError as exc:
            self._fail(job, exc.error, exc.detail)
        except Exception as exc:  # noqa: BLE001 - a job must end, never hang "running"
            logger.exception("demo purchase %s crashed", job.job_id)
            self._fail(job, "INTERNAL", f"{type(exc).__name__}: {exc}")
        finally:
            job.finished_at = _now()
            with self._lock:
                if self._running == job.job_id:
                    self._running = None

    def _fail(self, job: Job, code: str, detail: str) -> None:
        job.status = "failed"
        failed_step = None
        for step in job.steps:
            if step.status == "running":
                step.status, step.detail, step.finished_at = "failed", detail, _now()
                failed_step = step.key
            elif step.status == "pending":
                step.status = "skipped"
        job.error = {"code": code, "detail": detail, "step": failed_step or ""}

    @staticmethod
    def _tx(step: Step, tx_hash: str | None) -> None:
        if tx_hash:
            step.tx_hash, step.tx_url = tx_hash, settings.tx_url(tx_hash)

    # --- steps --------------------------------------------------------------------------

    def _step_fund_agent(self, job: Job, step: Step, ctx: dict) -> None:
        treasury = Keypair.from_secret(settings.demo_treasury_secret)
        usdc = Asset(settings.usdc_asset_code, settings.usdc_classic_issuer)
        price = Decimal(settings.price_base_units) / SAC_DECIMALS
        horizon = self._horizon_server()

        try:
            balances = horizon.accounts().account_id(treasury.public_key).call()["balances"]
        except Exception as exc:  # noqa: BLE001
            raise DemoStepFailed(
                "TREASURY_UNREADABLE", f"could not read the treasury: {exc}"
            ) from exc
        xlm = next(
            (Decimal(b["balance"]) for b in balances if b["asset_type"] == "native"), Decimal(0)
        )
        usdc_balance = next(
            (
                Decimal(b["balance"])
                for b in balances
                if b.get("asset_code") == usdc.code and b.get("asset_issuer") == usdc.issuer
            ),
            Decimal(0),
        )
        needed_xlm = Decimal(settings.demo_agent_starting_xlm) + Decimal(1)
        if usdc_balance < price or xlm < needed_xlm:
            raise DemoStepFailed(
                "TREASURY_LOW",
                f"demo treasury holds {usdc_balance} USDC and {xlm} XLM; "
                f"one purchase needs {price} USDC and {needed_xlm} XLM",
            )

        agent = Keypair.random()
        ctx["agent"] = agent
        job.agent = agent.public_key
        try:
            source = horizon.load_account(treasury.public_key)
            tx = (
                TransactionBuilder(source, settings.network_passphrase, base_fee=1000)
                .append_create_account_op(
                    destination=agent.public_key,
                    starting_balance=settings.demo_agent_starting_xlm,
                )
                .append_change_trust_op(asset=usdc, source=agent.public_key)
                .append_payment_op(destination=agent.public_key, asset=usdc, amount=str(price))
                .set_timeout(120)
                .build()
            )
            tx.sign(treasury)
            tx.sign(agent)
            tx_hash = horizon.submit_transaction(tx)["hash"]
        except Exception as exc:  # noqa: BLE001
            raise DemoStepFailed("FUNDING_FAILED", f"could not fund the agent: {exc}") from exc

        self._tx(step, tx_hash)
        step.detail = f"agent {agent.public_key} holds {price} USDC"
        step.data = {"agent": agent.public_key, "usdc": str(price)}

    def _step_challenge(self, job: Job, step: Step, ctx: dict) -> None:
        response = ctx["http"].get(f"/use/{job.skill_id}/{job.version}")
        header = response.headers.get(x402.PAYMENT_REQUIRED_HEADER)
        if response.status_code != 402 or not header:
            raise DemoStepFailed(
                "CHALLENGE_UNEXPECTED",
                f"expected 402 with a payment challenge, got {response.status_code}: "
                f"{response.text[:200]}",
            )
        required = x402.decode_header(header)
        offer = required["accepts"][0]
        ctx["payment_required"] = required
        step.detail = "HTTP 402 Payment Required"
        step.data = {
            "status": 402,
            "amount": offer["amount"],
            "amount_usdc": str(Decimal(offer["amount"]) / SAC_DECIMALS),
            "asset": offer["asset"],
            "pay_to": offer["payTo"],
            "network": offer["network"],
        }

    def _step_sign_payment(self, job: Job, step: Step, ctx: dict) -> None:
        agent: Keypair = ctx["agent"]
        try:
            payment = x402_client.build_payment(
                ctx["payment_required"],
                agent,
                rpc_url=settings.rpc_url,
                horizon_url=settings.horizon_url,
                network=x402.NETWORK,
            )
        except x402_client.PaymentBuildError as exc:
            raise DemoStepFailed("PAYMENT_BUILD_FAILED", exc.reason) from exc
        ctx["payment"] = payment
        step.detail = "authorization entry signed by the agent; no XLM needed, fees are sponsored"
        step.data = {"payer": agent.public_key, "amount": payment["accepted"]["amount"]}

    def _step_pay(self, job: Job, step: Step, ctx: dict) -> None:
        # No X-AGENT-ADDRESS: the API must learn the payer from the facilitator's verify,
        # the only source it trusts after payment (STE-42).
        response = ctx["http"].get(
            f"/use/{job.skill_id}/{job.version}",
            headers={x402.PAYMENT_HEADER: x402.encode_header(ctx["payment"])},
        )
        if response.status_code != 200:
            try:
                body = response.json()
                code, detail = body.get("error", "PAYMENT_FAILED"), body.get("detail", "")
            except ValueError:
                code, detail = "PAYMENT_FAILED", response.text[:200]
            raise DemoStepFailed(code, f"paid request answered {response.status_code}: {detail}")

        licence = response.headers.get("X-STERISH-LICENSE")
        settle_tx = response.headers.get("X-STERISH-SETTLEMENT-TX")
        mint_tx = response.headers.get("X-STERISH-LICENSE-TX")
        if licence != "minted" or not settle_tx or not mint_tx:
            raise DemoStepFailed(
                "PAYMENT_UNEXPECTED",
                f"expected a minted licence with settlement and mint tx, got licence={licence}",
            )
        ctx["served"] = response.content
        self._tx(step, mint_tx)
        step.detail = "payment settled and licence minted"
        step.data = {
            "settlement_tx": settle_tx,
            "settlement_tx_url": settings.tx_url(settle_tx),
            "mint_tx": mint_tx,
            "mint_tx_url": settings.tx_url(mint_tx),
        }

    def _step_verify_bytes(self, job: Job, step: Step, ctx: dict) -> None:
        import json

        from sterish_pipeline.content_hash import content_hash

        files = json.loads(ctx["served"])
        served_hash = content_hash({name: text.encode("utf-8") for name, text in files.items()})
        onchain_hash = ctx["record"]["content_hash"]
        if served_hash != onchain_hash:
            raise DemoStepFailed(
                "BYTES_MISMATCH", f"served bytes hash to {served_hash}, chain says {onchain_hash}"
            )
        step.detail = "content_hash(served bytes) matches the registry"
        step.data = {"content_hash": onchain_hash, "files": sorted(files)}

    def _step_licence_on_chain(self, job: Job, step: Step, ctx: dict) -> None:
        agent: Keypair = ctx["agent"]
        if not chain.has_license(agent.public_key, job.skill_id, job.version):
            raise DemoStepFailed(
                "LICENCE_NOT_FOUND", "the tokens contract does not report the licence"
            )
        step.detail = "has_license returned true"
        step.data = {
            "tokens_contract_id": settings.tokens_contract_id,
            "contract_url": settings.contract_url(settings.tokens_contract_id),
        }

    def _step_repeat_free(self, job: Job, step: Step, ctx: dict) -> None:
        agent: Keypair = ctx["agent"]
        # Since STE-48 naming the holder is not enough: the free path wants a SEP-53
        # signature over a single-use challenge. The demo holds the agent's key, so it
        # proves ownership exactly as an outside agent would.
        challenge = ctx["http"].get(
            f"/use/{job.skill_id}/{job.version}/challenge",
            params={"agent": agent.public_key},
        )
        if challenge.status_code != 200:
            raise DemoStepFailed(
                "REPEAT_NOT_FREE",
                f"ownership challenge answered {challenge.status_code}",
            )
        body = challenge.json()
        signature = base64.b64encode(agent.sign(proofs.sep53_digest(body["message"]))).decode()
        response = ctx["http"].get(
            f"/use/{job.skill_id}/{job.version}",
            headers={
                "X-AGENT-ADDRESS": agent.public_key,
                proofs.NONCE_HEADER: body["nonce"],
                proofs.SIGNATURE_HEADER: signature,
            },
        )
        if response.status_code != 200 or response.headers.get("X-STERISH-LICENSE") != "held":
            raise DemoStepFailed(
                "REPEAT_NOT_FREE",
                f"expected 200 held, got {response.status_code} "
                f"licence={response.headers.get('X-STERISH-LICENSE')}",
            )
        step.detail = "HTTP 200, served from the licence with a SEP-53 ownership proof, no payment"
        step.data = {"status": 200, "licence": "held"}


buyer = DemoBuyer()
