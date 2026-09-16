#!/usr/bin/env python3
"""STE-27 — run the full Sterish loop against the live testnet stack and record it.

Every step writes its evidence the moment it happens (step -> action -> outcome ->
tx hash / URL) to `evidence.jsonl`, and the Markdown evidence document is rendered
from that file at the end. Nothing is narrated afterwards, and nothing is retried
until it looks clean: a step that fails is recorded as failed, with its error, and
the run moves on to the steps that do not depend on it.

These are real testnet transactions — real escrow locks, real USDC, real mints.

    uv run --project pipeline python docs/rehearsal/run_rehearsal.py \
        [--dashboard-url http://localhost:3000]

Requirements (see docs/rehearsal/README.md):

  * `.env` at the repo root with DEVELOPER_SECRET, AUDITOR_SECRET, DEPLOYER_SECRET
    and REPORTER_ADDRESS. Secrets are read, never printed; every string written to
    the evidence is scrubbed of them as a second line of defence.
  * DEVELOPER holding >= 0.8 USDC and AUDITOR >= 0.4 USDC (fee 0.1, bond 0.2, twice;
    plus 0.5 transferred to the fresh agent).
  * `npm ci` in demo/x402-buyer (the x402 client library).

Step statuses: GREEN, RED, PARTIAL, MANUAL REQUIRED, BLOCKED (a prerequisite step
did not produce what this one needs). Only GREEN counts as green.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from stellar_sdk import Address, Asset, Keypair, Server, TransactionBuilder, scval

from sterish_pipeline import onchain, orchestrator
from sterish_pipeline.audit import run_audit
from sterish_pipeline.config import TESTNET_PASSPHRASE, PipelineConfig
from sterish_pipeline.namespaces import new_test_skill_id
from sterish_pipeline.orchestrator import OrchestratorConfig

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

# The live stack, as of STE-44 (docs/deployments.md "Current addresses"). Pinned here
# rather than read from .env on purpose: a worktree .env written before the v2 redeploy
# still names the v1 pair, and a rehearsal that silently ran against v1 would prove
# nothing about the migration it exists to check.
LIVE = {
    "api": "https://api-sterish.jameshub.fun",
    "registry": "CCZJN366SV57JEBZVXGYY3ZBLJNFV4IR5ILCAI3EMX2WDNQPEPQ4BRL2",
    "tokens": "CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T",
    "escrow": "CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE",
    "usdc_sac": "CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA",
    "usdc_issuer": "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5",
}
RPC_URL = "https://soroban-testnet.stellar.org"
HORIZON_URL = "https://horizon-testnet.stellar.org"
FRIENDBOT_URL = "https://friendbot.stellar.org"
EXPERT = "https://stellar.expert/explorer/testnet"
EXPERT_API = "https://api.stellar.expert/explorer/testnet"

# Stroops (1 USDC = 10_000_000). The same small amounts as the STE-16 live suite:
# money only flows one way and refilling needs the Captcha-gated Circle faucet.
FEE = 1_000_000
BOND = 2_000_000
AGENT_FUNDING = "0.5"          # USDC moved from DEVELOPER to the fresh agent

HTTP_TIMEOUT = 120

STEP_TITLES = {
    0: "Preflight: live stack, roles and balances",
    1: "Developer submits a brand-new skill; escrow locks fee + bond",
    2: "Pipeline audits it -> SAFE on chain -> VERIFIED minted -> settle",
    3: "A fresh agent wallet checks the skill via the dashboard -> SAFE",
    4: "use without a licence -> 402 -> pay USDC over x402 -> licence minted -> 200",
    5: "The second call returns 200 directly",
    6: "Negative path: a poisoned skill -> DANGEROUS, blocked, cannot be bought",
    7: "Slash path on the live stack: bond -> reporter",
}


# --------------------------------------------------------------------------- evidence


class Evidence:
    """Append-only evidence log. Every row is flushed to disk before the next action."""

    def __init__(self, run_dir: Path, secrets: list[str]):
        self.run_dir = run_dir
        self.path = run_dir / "evidence.jsonl"
        self.rows: list[dict] = []
        self.steps: dict[int, dict] = {}
        self._secrets = [s for s in secrets if s]

    def add_secret(self, value: str) -> None:
        self._secrets.append(value)

    def scrub(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "<redacted>")
        return text

    def _write(self, row: dict) -> None:
        line = self.scrub(json.dumps(row, default=str))
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.rows.append(json.loads(line))

    def log(self, step: int, action: str, outcome: str, *, tx: str | None = None,
            url: str | None = None, detail: str = "", data: object = None) -> None:
        if tx and not url:
            url = f"{EXPERT}/tx/{tx}"
        row = {
            "kind": "action",
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "step": step, "action": action, "outcome": outcome,
            "tx": tx, "url": url, "detail": detail, "data": data,
        }
        self._write(row)
        print(self.scrub(f"[step {step}] {action:<40} {outcome:<5} {url or ''} {detail}"[:400]),
              flush=True)

    def conclude(self, step: int, status: str, summary: str) -> None:
        row = {
            "kind": "conclusion",
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "step": step, "status": status, "summary": summary,
        }
        self._write(row)
        self.steps[step] = row
        print(self.scrub(f"[step {step}] ==> {status}: {summary}"), flush=True)


# --------------------------------------------------------------------------- helpers


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def append_env(path: Path, lines: list[str]) -> None:
    """Persist a generated key the way CLAUDE.md requires: straight to .env, never echoed."""
    with path.open("a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(lines) + "\n")
    os.chmod(path, 0o600)


def usdc_balance(cfg: PipelineConfig, address: str) -> int:
    return int(onchain.simulate(cfg, LIVE["usdc_sac"], "balance",
                                [scval.to_address(Address(address))]) or 0)


def get_request(cfg: PipelineConfig, request_id: int) -> dict:
    return onchain.simulate(cfg, LIVE["escrow"], "get_request", [scval.to_uint32(request_id)])


def status_of(record: dict) -> str:
    status = record.get("status") if isinstance(record, dict) else None
    if isinstance(status, (list, tuple)) and status:
        status = status[0]
    return str(status)


def has_license(cfg: PipelineConfig, agent: str, skill_id: str, version: str) -> bool:
    return bool(onchain.simulate(cfg, LIVE["tokens"], "has_license", [
        scval.to_address(Address(agent)), scval.to_string(skill_id), scval.to_string(version),
    ]))


def is_verified_token(cfg: PipelineConfig, skill_id: str, version: str) -> bool:
    return bool(onchain.simulate(cfg, LIVE["tokens"], "is_verified_token",
                                 [scval.to_string(skill_id), scval.to_string(version)]))


def api_get(path: str, **kwargs) -> requests.Response:
    return requests.get(f"{LIVE['api']}{path}", timeout=HTTP_TIMEOUT, **kwargs)


def classic_tx(secret: str, build) -> str:
    """Sign and submit one classic transaction through Horizon. Returns its hash."""
    server = Server(HORIZON_URL)
    keypair = Keypair.from_secret(secret)
    account = server.load_account(keypair.public_key)
    builder = TransactionBuilder(account, TESTNET_PASSPHRASE, base_fee=1000).set_timeout(120)
    build(builder)
    tx = builder.build()
    tx.sign(keypair)
    return server.submit_transaction(tx)["hash"]


def fmt_usdc(stroops: int) -> str:
    sign = "-" if stroops < 0 else ""
    stroops = abs(stroops)
    return f"{sign}{stroops // 10_000_000}.{stroops % 10_000_000:07d}"


def prepare_skill(kind: str, slug: str, suffix: str, run_dir: Path) -> tuple[Path, str]:
    """Copy a rehearsal skill under a fresh test-namespace id, so the bytes are new.

    The id comes from `new_test_skill_id`, never an f-string: the registry is
    append-only, and only the `com.sterish.e2e-` prefix keeps a rehearsal entry out
    of the dashboard's default listing (CLAUDE.md, "Registry testnet").
    """
    skill_id = new_test_skill_id("e2e", slug, suffix)
    target = run_dir / "skills" / kind
    shutil.copytree(HERE / "skills" / kind, target)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["skill_id"] = skill_id
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target, skill_id


def audit(skill_dir: Path, cfg: PipelineConfig, run_dir: Path) -> dict:
    run = run_audit(skill_dir, config=cfg)          # all three stages, sandbox included
    run.validate(submittable=True)
    document = run.verdict_json()
    out = run_dir / "verdicts" / f"{document['skill_id']}@{document['version']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def x402_call(env: dict, mode: str, agent_secret: str, skill_id: str, version: str) -> dict:
    """Run docs/rehearsal/x402_pay.mjs with demo/x402-buyer as its module root."""
    buyer = REPO / "demo" / "x402-buyer"
    if not (buyer / "node_modules").is_dir():
        raise RuntimeError("demo/x402-buyer/node_modules missing; run `npm ci` there first")
    child_env = {
        "PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""),
        "STERISH_API": LIVE["api"], "STELLAR_RPC_URL": RPC_URL,
        "AGENT_SECRET": agent_secret, "SKILL_ID": skill_id, "SKILL_VERSION": version,
        "MODE": mode,
    }
    proc = subprocess.run(
        ["node", "--input-type=module"], input=(HERE / "x402_pay.mjs").read_text(),
        cwd=buyer, env=child_env, capture_output=True, text=True, timeout=300,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        raise RuntimeError(f"x402 helper produced no JSON (exit {proc.returncode}): "
                           f"{proc.stderr[-400:]}")
    return json.loads(lines[-1])


def find_usdc_debit_tx(agent: str, since: datetime) -> str | None:
    """The settlement transaction that moved the agent's USDC, found from the ledger.

    Needed because the API only returns the settlement receipt on a 200; when the
    purchase fails after settling, the response carries no transaction at all.
    """
    r = requests.get(f"{HORIZON_URL}/accounts/{agent}/effects",
                     params={"order": "desc", "limit": 20}, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        return None
    for effect in r.json().get("_embedded", {}).get("records", []):
        if effect.get("type") != "account_debited" or effect.get("asset_code") != "USDC":
            continue
        created = datetime.fromisoformat(effect["created_at"].replace("Z", "+00:00"))
        if created < since:
            continue
        op = requests.get(effect["_links"]["operation"]["href"], timeout=HTTP_TIMEOUT)
        if op.status_code == 200:
            return op.json().get("transaction_hash")
    return None


# --------------------------------------------------------------------------- the run


class Rehearsal:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.env_path = Path(args.env)
        self.env = load_env(self.env_path)
        for key in ("DEVELOPER_SECRET", "AUDITOR_SECRET", "DEPLOYER_SECRET", "REPORTER_ADDRESS"):
            if not self.env.get(key):
                sys.exit(f"{key} missing from {self.env_path}")
        self.started = datetime.now(timezone.utc)
        self.run_id = self.started.strftime("%Y-%m-%dT%H%M%SZ")
        self.suffix = str(int(self.started.timestamp()))
        self.run_dir = Path(args.out) / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        secrets = [v for k, v in self.env.items() if k.endswith("_SECRET")]
        self.ev = Evidence(self.run_dir, secrets)

        self.developer = Keypair.from_secret(self.env["DEVELOPER_SECRET"]).public_key
        self.auditor = Keypair.from_secret(self.env["AUDITOR_SECRET"]).public_key
        self.admin = Keypair.from_secret(self.env["DEPLOYER_SECRET"]).public_key
        self.reporter = self.env["REPORTER_ADDRESS"]
        self.use_llm = bool(os.environ.get("LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
        self.cfg = PipelineConfig(registry_contract_id=LIVE["registry"], rpc_url=RPC_URL,
                                  network_passphrase=TESTNET_PASSPHRASE, use_llm=self.use_llm)
        self.ctx: dict = {}

    def orch_config(self) -> OrchestratorConfig:
        return OrchestratorConfig(
            registry_id=LIVE["registry"], tokens_id=LIVE["tokens"], escrow_id=LIVE["escrow"],
            owner_secret=self.env["DEVELOPER_SECRET"],
            auditor_secret=self.env["AUDITOR_SECRET"],
            admin_secret=self.env["DEPLOYER_SECRET"],
            reports_dir=self.run_dir / "reports",
            report_base_url=LIVE["api"],
            journal_path=self.run_dir / "journal.json",
            run_escrow=False, fee_amount=FEE, bond_amount=BOND,
        )

    # ---- step runner

    def step(self, n: int, fn, needs: tuple[str, ...] = ()) -> None:
        missing = [k for k in needs if k not in self.ctx]
        if missing:
            self.ev.conclude(n, "BLOCKED",
                             f"prerequisite not produced by an earlier step: {', '.join(missing)}")
            return
        try:
            status, summary = fn(n)
        except Exception as exc:  # recorded, never swallowed
            detail = f"{type(exc).__name__}: {exc}"
            self.ev.log(n, "unhandled exception", "fail", detail=detail[:600],
                        data=traceback.format_exc()[-1500:])
            status, summary = "RED", f"aborted by {detail[:300]}"
        self.ev.conclude(n, status, summary)

    # ---- 0

    def s0_preflight(self, n: int):
        ok = True
        health = api_get("/health")
        body = health.json() if health.status_code == 200 else {}
        match = body.get("registry_contract_id") == LIVE["registry"]
        ok &= match
        self.ev.log(n, "API /health", "ok" if match else "fail", url=f"{LIVE['api']}/health",
                    detail=f"HTTP {health.status_code}, registry {body.get('registry_contract_id')}, "
                           f"rpc_reachable={body.get('rpc_reachable')}, "
                           f"facilitator_reachable={body.get('facilitator_reachable')}")

        for key in ("REGISTRY_CA", "TOKENS_CA", "ESCROW_CA"):
            live = LIVE[key.split("_")[0].lower()]
            if self.env.get(key) and self.env[key] != live:
                self.ev.log(n, f".env {key}", "info",
                            detail=f".env names {self.env[key]}, live is {live}; "
                                   "the run uses the live address")

        roles = {
            "tokens.get_registry": (onchain.simulate(self.cfg, LIVE["tokens"], "get_registry"), LIVE["registry"]),
            "tokens.get_auditor_role": (onchain.simulate(self.cfg, LIVE["tokens"], "get_auditor_role"), self.auditor),
            "tokens.get_minter_role": (onchain.simulate(self.cfg, LIVE["tokens"], "get_minter_role"), self.admin),
            "registry.get_auditor": (onchain.simulate(self.cfg, LIVE["registry"], "get_auditor"), self.auditor),
            "escrow.get_usdc_token": (onchain.simulate(self.cfg, LIVE["escrow"], "get_usdc_token"), LIVE["usdc_sac"]),
            "escrow.get_admin": (onchain.simulate(self.cfg, LIVE["escrow"], "get_admin"), self.admin),
        }
        for name, (got, want) in roles.items():
            got_s = getattr(got, "address", str(got))
            good = got_s == want
            ok &= good
            self.ev.log(n, name, "ok" if good else "fail", url=f"{EXPERT}/contract/"
                        f"{LIVE[name.split('.')[0]]}", detail=f"{got_s} (expected {want})")

        for who, addr in (("developer", self.developer), ("auditor", self.auditor),
                          ("admin", self.admin), ("reporter", self.reporter)):
            self.ev.log(n, f"USDC balance {who}", "info", url=f"{EXPERT}/account/{addr}",
                        detail=f"{addr} holds {fmt_usdc(usdc_balance(self.cfg, addr))} USDC")
        self.ev.log(n, "stage 3 LLM", "info",
                    detail="enabled" if self.use_llm else
                    "disabled: no LLM_API_KEY/ANTHROPIC_API_KEY in this environment; "
                    "verdicts are the deterministic policy (stage 3 is advisory)")
        return ("GREEN" if ok else "RED",
                "API serves Registry v2; Tokens v2 roles and Escrow wiring match the expected accounts"
                if ok else "live stack does not match the expected wiring (see rows)")

    # ---- 1

    def s1_submit_and_lock(self, n: int):
        skill_dir, skill_id = prepare_skill("safe", "rehearsal-unit-converter", self.suffix, self.run_dir)
        version = "1.0.0"
        self.ctx["safe_dir"], self.ctx["safe_id"], self.ctx["safe_version"] = skill_dir, skill_id, version
        self.ev.log(n, "brand-new skill prepared", "info",
                    detail=f"{skill_id}@{version} from docs/rehearsal/skills/safe (never seeded)")

        before = {w: usdc_balance(self.cfg, a) for w, a in
                  (("developer", self.developer), ("auditor", self.auditor), ("escrow", LIVE["escrow"]))}
        created = onchain.create_audit_request(self.cfg, LIVE["escrow"], self.env["DEVELOPER_SECRET"],
                                               skill_id, version, FEE, BOND)
        request_id = created.value if isinstance(created.value, int) else None
        self.ev.log(n, "escrow.create_audit_request (developer)", "ok" if request_id is not None else "fail",
                    tx=created.tx_hash, detail=f"request_id={request_id}, fee {fmt_usdc(FEE)} USDC")
        if request_id is None:
            return "RED", "create_audit_request returned no request_id; refusing to guess one"

        bonded = onchain.post_bond(self.cfg, LIVE["escrow"], self.env["AUDITOR_SECRET"], request_id)
        self.ev.log(n, "escrow.post_bond (auditor)", "ok", tx=bonded.tx_hash,
                    detail=f"bond {fmt_usdc(BOND)} USDC")

        record = get_request(self.cfg, request_id)
        after = {w: usdc_balance(self.cfg, a) for w, a in
                 (("developer", self.developer), ("auditor", self.auditor), ("escrow", LIVE["escrow"]))}
        deltas = {w: after[w] - before[w] for w in before}
        expected = {"developer": -FEE, "auditor": -BOND, "escrow": FEE + BOND}
        good = deltas == expected and status_of(record) == "Bonded"
        self.ev.log(n, "read back escrow.get_request + balances", "ok" if good else "fail",
                    url=f"{EXPERT}/contract/{LIVE['escrow']}",
                    detail=f"status={status_of(record)}; deltas " +
                           ", ".join(f"{w} {fmt_usdc(d)}" for w, d in deltas.items()) +
                           f" (expected escrow +{fmt_usdc(FEE + BOND)})")
        if good:
            self.ctx["safe_request_id"] = request_id
            self.ctx["balances_before_lock"] = before
        return ("GREEN" if good else "RED",
                f"request #{request_id} Bonded; escrow holds fee+bond {fmt_usdc(FEE + BOND)} USDC"
                if good else "escrow state or balance deltas differ from a fee+bond lock")

    # ---- 2

    def s2_audit_verdict_mint_settle(self, n: int):
        skill_id, version = self.ctx["safe_id"], self.ctx["safe_version"]
        document = audit(self.ctx["safe_dir"], self.cfg, self.run_dir)
        self.ev.log(n, "pipeline audit (3 stages)", "ok" if document["verdict"] == "SAFE" else "fail",
                    detail=f"verdict {document['verdict']}, score {document['score']}, "
                           f"content_hash {document['content_hash']}")
        if document["verdict"] != "SAFE":
            return "RED", f"pipeline returned {document['verdict']} for the safe skill"

        result = orchestrator.orchestrate(document, self.orch_config(), self.cfg)
        for s in result.steps:
            self.ev.log(n, f"orchestrator {s.step}", "ok" if s.status in ("done", "skipped") else "fail",
                        tx=s.tx_hash, detail=f"{s.status} {s.detail}".strip())
        if not result.ok:
            return "RED", "orchestrator reported a failed or unknown step"

        record = onchain.lookup_by_hash(self.cfg, LIVE["registry"], document["content_hash"])
        verdict = (record or {}).get("verdict")
        verified = onchain.is_verified(self.cfg, LIVE["registry"], skill_id, version)
        badge = is_verified_token(self.cfg, skill_id, version)
        chain_ok = bool(record) and verdict == ["Safe"] and verified and badge
        self.ev.log(n, "read back registry.lookup_by_hash / is_verified / tokens.is_verified_token",
                    "ok" if chain_ok else "fail", url=f"{EXPERT}/contract/{LIVE['registry']}",
                    detail=f"verdict={verdict}, score={(record or {}).get('trust_score')}, "
                           f"registry.is_verified={verified}, tokens.is_verified_token={badge}")

        request_id = self.ctx["safe_request_id"]
        settled = onchain.settle(self.cfg, LIVE["escrow"], self.env["DEPLOYER_SECRET"], request_id)
        req = get_request(self.cfg, request_id)
        before = self.ctx["balances_before_lock"]
        after = {w: usdc_balance(self.cfg, a) for w, a in
                 (("developer", self.developer), ("auditor", self.auditor), ("escrow", LIVE["escrow"]))}
        deltas = {w: after[w] - before[w] for w in before}
        expected = {"developer": -FEE, "auditor": FEE, "escrow": 0}
        settle_ok = status_of(req) == "Settled" and deltas == expected
        self.ev.log(n, "escrow.settle (admin)", "ok" if settle_ok else "fail", tx=settled.tx_hash,
                    detail=f"status={status_of(req)}; net since the lock " +
                           ", ".join(f"{w} {fmt_usdc(d)}" for w, d in deltas.items()))

        good = chain_ok and settle_ok
        if chain_ok:
            self.ctx["safe_hash"] = document["content_hash"]
        return ("GREEN" if good else "RED",
                f"SAFE score {document['score']} on Registry v2, VERIFIED badge on Tokens v2, "
                f"request #{request_id} settled (auditor +{fmt_usdc(FEE)} net)"
                if good else "verdict, badge or settlement did not read back as expected")

    # ---- 3

    def s3_agent_checks(self, n: int):
        skill_id, version, content_hash = self.ctx["safe_id"], self.ctx["safe_version"], self.ctx["safe_hash"]
        agent = Keypair.random()
        self.ev.add_secret(agent.secret)
        append_env(self.env_path, [
            f"# STE-27 rehearsal agent, run {self.run_id} (TESTNET ONLY - JANGAN COMMIT)",
            f"REHEARSAL_AGENT_{self.suffix}_ADDRESS={agent.public_key}",
            f"REHEARSAL_AGENT_{self.suffix}_SECRET={agent.secret}",
        ])
        self.ev.log(n, "fresh agent keypair", "info", url=f"{EXPERT}/account/{agent.public_key}",
                    detail=f"{agent.public_key} (secret written to .env only)")

        fb = requests.get(FRIENDBOT_URL, params={"addr": agent.public_key}, timeout=HTTP_TIMEOUT)
        fb_hash = fb.json().get("hash") if fb.status_code == 200 else None
        self.ev.log(n, "setup: Friendbot XLM", "ok" if fb_hash else "fail", tx=fb_hash,
                    detail=f"HTTP {fb.status_code}")
        usdc = Asset("USDC", LIVE["usdc_issuer"])
        trust = classic_tx(agent.secret, lambda b: b.append_change_trust_op(usdc))
        self.ev.log(n, "setup: USDC trustline (agent)", "ok", tx=trust)
        funded = classic_tx(self.env["DEVELOPER_SECRET"], lambda b: b.append_payment_op(
            agent.public_key, usdc, AGENT_FUNDING))
        self.ev.log(n, "setup: 0.5 USDC developer -> agent", "ok", tx=funded,
                    detail="scripted transfer from a team account; the Circle faucet is Captcha-gated")
        self.ctx["agent"] = agent

        ok = True
        for path in (f"/check/by-hash/{content_hash}", f"/check/{skill_id}/{version}"):
            r = api_get(path)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            good = (r.status_code == 200 and body.get("verdict") == "SAFE"
                    and body.get("is_verified") is True and body.get("skill_id") == skill_id)
            ok &= good
            self.ev.log(n, f"API GET {path.split('/')[1]}{'/by-hash' if 'by-hash' in path else ''}",
                        "ok" if good else "fail", url=f"{LIVE['api']}{path}",
                        detail=f"HTTP {r.status_code}, verdict={body.get('verdict')}, "
                               f"is_verified={body.get('is_verified')}, trust_score={body.get('trust_score')}")
        lic = api_get(f"/license/{skill_id}/{version}", params={"agent": agent.public_key})
        held = lic.json().get("held") if lic.status_code == 200 else None
        self.ev.log(n, "API GET /license (baseline)", "ok" if held is False else "fail",
                    url=f"{LIVE['api']}/license/{skill_id}/{version}?agent={agent.public_key}",
                    detail=f"HTTP {lic.status_code}, held={held}")
        ok &= held is False

        dash = self.args.dashboard_url
        if not dash:
            self.ev.log(n, "dashboard skill page", "manual",
                        detail="no dashboard URL given and none is documented in the repo")
            return ("PARTIAL" if ok else "RED",
                    "API check SAFE (the endpoint the dashboard reads); dashboard not exercised")
        page_url = f"{dash.rstrip('/')}/skills/{skill_id}"
        page = requests.get(page_url, timeout=HTTP_TIMEOUT)
        rendered = page.status_code == 200 and "Audited safe, for exactly these bytes" in page.text \
            and skill_id in page.text
        self.ev.log(n, "dashboard /skills/<id> rendered", "ok" if rendered else "fail", url=page_url,
                    detail=f"HTTP {page.status_code}, SAFE banner present={rendered}")
        public = urlparse(dash).hostname not in ("localhost", "127.0.0.1", "0.0.0.0")
        if ok and rendered and public:
            return "GREEN", "API and the public dashboard both show SAFE for the new skill"
        if ok and rendered:
            return ("PARTIAL", "SAFE via the API and via the dashboard code pointed at the live API, "
                               "but the dashboard ran locally: there is no public dashboard URL")
        return "RED", "the check did not show SAFE (see rows)"

    # ---- 4

    def s4_buy(self, n: int):
        agent: Keypair = self.ctx["agent"]
        skill_id, version = self.ctx["safe_id"], self.ctx["safe_version"]
        before = usdc_balance(self.cfg, agent.public_key)
        started = datetime.now(timezone.utc)
        out = x402_call(self.env, "buy", agent.secret, skill_id, version)
        (self.run_dir / "x402-step4.json").write_text(self.ev.scrub(json.dumps(out, indent=2)) + "\n")
        reqs = {r["label"]: r for r in out.get("requests", [])}
        unpaid, paid = reqs.get("unpaid"), reqs.get("paid")
        use_url = out.get("url")
        if out.get("error"):
            self.ev.log(n, "x402 client error", "fail", detail=out["error"])

        got402 = bool(unpaid) and unpaid["status"] == 402 and unpaid["payment_required"]
        price = int((out.get("accepts") or {}).get("amount") or 0)
        self.ev.log(n, "GET /use without licence", "ok" if got402 else "fail", url=use_url,
                    detail=f"HTTP {unpaid and unpaid['status']}, PAYMENT-REQUIRED present="
                           f"{unpaid and unpaid['payment_required']}, price {fmt_usdc(price)} USDC, "
                           f"payTo {(out.get('accepts') or {}).get('payTo')}")
        if not paid:
            return "RED", "no paid request was made (see the 402 row)"

        time.sleep(6)   # let the settlement ledger close before reading balances
        after = usdc_balance(self.cfg, agent.public_key)
        licensed = has_license(self.cfg, agent.public_key, skill_id, version)
        receipt = paid.get("payment_response") or {}
        settle_tx = receipt.get("transaction") or find_usdc_debit_tx(agent.public_key, started)
        self.ev.log(n, "x402 settlement (agent USDC debit)", "ok" if before - after == price else "fail",
                    tx=settle_tx, detail=f"agent {fmt_usdc(before)} -> {fmt_usdc(after)} USDC "
                                         f"(debit {fmt_usdc(before - after)}); tx from "
                                         f"{'payment receipt' if receipt.get('transaction') else 'Horizon effects'}")
        self.ev.log(n, "GET /use with X-PAYMENT", "ok" if paid["status"] == 200 else "fail", url=use_url,
                    detail=f"HTTP {paid['status']}, X-STERISH-LICENSE={paid['license']}, "
                           f"body: {paid['body_excerpt'][:200]}")
        self.ev.log(n, "licence mint", "ok" if licensed else "fail", tx=paid.get("license_tx"),
                    url=None if paid.get("license_tx") else f"{EXPERT}/contract/{LIVE['tokens']}",
                    detail=f"tokens.has_license(agent)={licensed}; mint tx "
                           f"{'from X-STERISH-LICENSE-TX' if paid.get('license_tx') else 'not returned by the API'}")
        if licensed:
            self.ctx["licensed"] = True
        good = got402 and paid["status"] == 200 and paid["license"] == "minted" and licensed \
            and before - after == price
        if good:
            return "GREEN", f"402 -> paid {fmt_usdc(price)} USDC -> licence minted -> 200"
        return ("RED", f"paid {fmt_usdc(before - after)} USDC, licence on chain={licensed}, "
                       f"but /use answered HTTP {paid['status']} instead of 200 with the artifact")

    # ---- 5

    def s5_second_call(self, n: int):
        agent: Keypair = self.ctx["agent"]
        skill_id, version = self.ctx["safe_id"], self.ctx["safe_version"]
        before = usdc_balance(self.cfg, agent.public_key)
        out = x402_call(self.env, "held", agent.secret, skill_id, version)
        (self.run_dir / "x402-step5.json").write_text(self.ev.scrub(json.dumps(out, indent=2)) + "\n")
        held = (out.get("requests") or [{}])[0]
        after = usdc_balance(self.cfg, agent.public_key)
        good = held.get("status") == 200 and held.get("license") == "held" and after == before
        self.ev.log(n, "GET /use with X-AGENT-ADDRESS only", "ok" if good else "fail", url=out.get("url"),
                    detail=f"HTTP {held.get('status')}, X-STERISH-LICENSE={held.get('license')}, "
                           f"PAYMENT-REQUIRED={held.get('payment_required')}, agent balance unchanged="
                           f"{after == before}, body: {str(held.get('body_excerpt'))[:200]}")
        lic = api_get(f"/license/{skill_id}/{version}", params={"agent": agent.public_key})
        self.ev.log(n, "API GET /license", "info",
                    url=f"{LIVE['api']}/license/{skill_id}/{version}?agent={agent.public_key}",
                    detail=f"HTTP {lic.status_code}, held={lic.json().get('held') if lic.ok else None}")
        if good:
            return "GREEN", "second call served from the held licence, no payment"
        return ("RED", f"second call answered HTTP {held.get('status')} "
                       f"(licence header {held.get('license')}), not 200 held")

    # ---- 6

    def s6_poisoned(self, n: int):
        skill_dir, skill_id = prepare_skill("poisoned", "rehearsal-pdf-summarizer", self.suffix, self.run_dir)
        version = "1.0.0"
        self.ctx["poison_id"] = skill_id
        document = audit(skill_dir, self.cfg, self.run_dir)
        dangerous = document["verdict"] == "DANGEROUS"
        self.ev.log(n, "pipeline audit (3 stages)", "ok" if dangerous else "fail",
                    detail=f"verdict {document['verdict']}, score {document['score']}, "
                           f"{len(document['findings'])} findings, content_hash {document['content_hash']}")
        if not dangerous:
            return "RED", f"poisoned skill audited as {document['verdict']}, gate requires DANGEROUS"

        result = orchestrator.orchestrate(document, self.orch_config(), self.cfg)
        for s in result.steps:
            self.ev.log(n, f"orchestrator {s.step}", "ok" if s.status in ("done", "skipped") else "fail",
                        tx=s.tx_hash, detail=f"{s.status} {s.detail}".strip())

        badge = is_verified_token(self.cfg, skill_id, version)
        verified = onchain.is_verified(self.cfg, LIVE["registry"], skill_id, version)
        self.ev.log(n, "read back registry.is_verified / tokens.is_verified_token",
                    "ok" if not badge and not verified else "fail",
                    url=f"{EXPERT}/contract/{LIVE['tokens']}",
                    detail=f"registry.is_verified={verified}, tokens.is_verified_token={badge}")

        path = f"/check/by-hash/{document['content_hash']}"
        r = api_get(path)
        body = r.json() if r.ok else {}
        check_ok = body.get("verdict") == "DANGEROUS" and body.get("is_verified") is False
        self.ev.log(n, "API GET /check/by-hash", "ok" if check_ok else "fail", url=f"{LIVE['api']}{path}",
                    detail=f"HTTP {r.status_code}, verdict={body.get('verdict')}, "
                           f"is_verified={body.get('is_verified')}")

        agent: Keypair | None = self.ctx.get("agent")
        use_path = f"/use/{skill_id}/{version}"
        headers = {"X-AGENT-ADDRESS": agent.public_key} if agent else {}
        use = api_get(use_path, headers=headers)
        use_body = use.json() if use.headers.get("content-type", "").startswith("application/json") else {}
        blocked = use.status_code == 403 and use_body.get("error") == "NOT_VERIFIED" \
            and "PAYMENT-REQUIRED" not in use.headers
        self.ev.log(n, "API GET /use (attempt to buy)", "ok" if blocked else "fail",
                    url=f"{LIVE['api']}{use_path}",
                    detail=f"HTTP {use.status_code}, error={use_body.get('error')}, "
                           f"PAYMENT-REQUIRED offered={'PAYMENT-REQUIRED' in use.headers}")

        # The contract's own refusal, independent of the API. `invoke` simulates before
        # it submits, so a refused mint never reaches the ledger.
        buyer = agent.public_key if agent else self.developer
        try:
            refused_tx = onchain.invoke(self.cfg, LIVE["tokens"], "mint_license", [
                scval.to_address(Address(buyer)), scval.to_string(skill_id), scval.to_string(version),
            ], self.env["DEPLOYER_SECRET"], retries=1)
            self.ev.log(n, "tokens.mint_license (minter) on DANGEROUS", "fail", tx=refused_tx.tx_hash,
                        detail="the contract MINTED a licence for a DANGEROUS version")
            chain_refused = False
        except onchain.ContractCallError as exc:
            chain_refused = True
            self.ev.log(n, "tokens.mint_license (minter) on DANGEROUS", "ok",
                        detail=f"refused in simulation, nothing submitted: contract error #{exc.code} "
                               f"(tokens ABI; the pipeline's error table labels it '{exc}')")

        dash = self.args.dashboard_url
        if dash:
            page_url = f"{dash.rstrip('/')}/skills/{skill_id}"
            page = requests.get(page_url, timeout=HTTP_TIMEOUT)
            shown = page.status_code == 200 and "Do not install this version" in page.text
            self.ev.log(n, "dashboard /skills/<id> rendered", "ok" if shown else "fail", url=page_url,
                        detail=f"HTTP {page.status_code}, DANGEROUS banner present={shown}")

        good = result.ok and not badge and not verified and check_ok and blocked and chain_refused
        return ("GREEN" if good else "RED",
                "DANGEROUS on chain, no badge, API 403 with no payment offer, contract refuses the mint"
                if good else "the poisoned skill was not fully blocked (see rows)")

    # ---- 7

    def s7_slash(self, n: int):
        skill_id, version = self.ctx["poison_id"], "1.0.0"
        parties = (("reporter", self.reporter), ("developer", self.developer),
                   ("auditor", self.auditor), ("escrow", LIVE["escrow"]))
        before = {w: usdc_balance(self.cfg, a) for w, a in parties}
        created = onchain.create_audit_request(self.cfg, LIVE["escrow"], self.env["DEVELOPER_SECRET"],
                                               skill_id, version, FEE, BOND)
        request_id = created.value if isinstance(created.value, int) else None
        self.ev.log(n, "escrow.create_audit_request (developer)", "ok" if request_id is not None else "fail",
                    tx=created.tx_hash, detail=f"request_id={request_id} for {skill_id}")
        if request_id is None:
            return "RED", "create_audit_request returned no request_id"
        bonded = onchain.post_bond(self.cfg, LIVE["escrow"], self.env["AUDITOR_SECRET"], request_id)
        self.ev.log(n, "escrow.post_bond (auditor)", "ok", tx=bonded.tx_hash)
        slashed = onchain.slash(self.cfg, LIVE["escrow"], self.env["DEPLOYER_SECRET"], request_id, self.reporter)
        req = get_request(self.cfg, request_id)
        after = {w: usdc_balance(self.cfg, a) for w, a in parties}
        deltas = {w: after[w] - before[w] for w in before}
        expected = {"reporter": BOND, "developer": 0, "auditor": -BOND, "escrow": 0}
        good = deltas == expected and status_of(req) == "Slashed"
        self.ev.log(n, "escrow.slash (admin) -> reporter", "ok" if good else "fail", tx=slashed.tx_hash,
                    detail=f"status={status_of(req)}; deltas " +
                           ", ".join(f"{w} {fmt_usdc(d)}" for w, d in deltas.items()))
        return ("GREEN" if good else "RED",
                f"request #{request_id} slashed: reporter +{fmt_usdc(BOND)}, fee refunded, auditor -{fmt_usdc(BOND)}"
                if good else "slash balances or status differ from expected")

    # ---- links

    def verify_links(self) -> list[dict]:
        """Every tx link must resolve. Checked against stellar.expert's own API (the page
        behind the link) and Horizon (the ledger), after giving the indexer time."""
        checks = []
        txs = [r for r in self.ev.rows if r.get("kind") == "action" and r.get("tx")]
        time.sleep(20)
        for row in txs:
            tx = row["tx"]
            expert = horizon = None
            for _ in range(6):
                expert = requests.get(f"{EXPERT_API}/tx/{tx}", timeout=HTTP_TIMEOUT).status_code
                horizon_r = requests.get(f"{HORIZON_URL}/transactions/{tx}", timeout=HTTP_TIMEOUT)
                horizon = horizon_r.status_code
                if expert == 200 and horizon == 200:
                    break
                time.sleep(10)
            successful = horizon_r.json().get("successful") if horizon == 200 else None
            checks.append({"step": row["step"], "action": row["action"], "tx": tx,
                           "stellar_expert": expert, "horizon": horizon, "successful": successful})
        return checks

    # ---- render

    def render(self, link_checks: list[dict]) -> Path:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                                capture_output=True, text=True).stdout.strip()
        green = sum(1 for k in range(1, 8) if self.ev.steps.get(k, {}).get("status") == "GREEN")
        lines = [
            f"# STE-27 rehearsal evidence — run `{self.run_id}`",
            "",
            "> **Generated by `docs/rehearsal/run_rehearsal.py` from `evidence.jsonl`.** Not edited by hand.",
            "> Findings, owners and tickets are in [`../../FINDINGS.md`](../../FINDINGS.md).",
            "> Testnet resets to genesis on **16 December 2026**; every stellar.expert link below expires then.",
            "",
            f"**{green} / 7 steps GREEN.**",
            "",
            "| | |", "|---|---|",
            f"| Started (UTC) | {self.started.isoformat(timespec='seconds')} |",
            f"| Repo commit | `{commit}` |",
            f"| API | {LIVE['api']} |",
            f"| Dashboard | {self.args.dashboard_url or '— (none given)'} |",
            f"| Registry v2 | [`{LIVE['registry']}`]({EXPERT}/contract/{LIVE['registry']}) |",
            f"| Tokens v2 | [`{LIVE['tokens']}`]({EXPERT}/contract/{LIVE['tokens']}) |",
            f"| Escrow (v1, unchanged) | [`{LIVE['escrow']}`]({EXPERT}/contract/{LIVE['escrow']}) |",
            f"| USDC SAC | [`{LIVE['usdc_sac']}`]({EXPERT}/contract/{LIVE['usdc_sac']}) |",
            f"| Fee / bond | {fmt_usdc(FEE)} / {fmt_usdc(BOND)} USDC |",
            f"| Stage 3 LLM | {'on' if self.use_llm else 'off (no key in the environment)'} |",
            "",
            "## Summary", "",
            "| # | Step | Status | Summary |", "|---|---|---|---|",
        ]
        for k in range(0, 8):
            c = self.ev.steps.get(k, {})
            lines.append(f"| {k} | {STEP_TITLES[k]} | **{c.get('status', 'NOT RUN')}** | {c.get('summary', '')} |")
        for k in range(0, 8):
            lines += ["", f"## Step {k} — {STEP_TITLES[k]}", "",
                      "| Time (UTC) | Action | Outcome | Link | Detail |", "|---|---|---|---|---|"]
            for r in self.ev.rows:
                if r.get("kind") != "action" or r["step"] != k:
                    continue
                link = ""
                if r.get("tx"):
                    link = f"[`{r['tx'][:16]}…`]({r['url']})"
                elif r.get("url"):
                    link = f"[link]({r['url']})"
                detail = str(r.get("detail", "")).replace("|", "\\|").replace("\n", " ")
                lines.append(f"| {r['at'][11:19]} | {r['action']} | {r['outcome']} | {link} | {detail} |")
            c = self.ev.steps.get(k)
            if c:
                lines += ["", f"**{c['status']}** — {c['summary']}"]
        lines += ["", "## Link check", "",
                  "Each transaction above, fetched after the run from stellar.expert's API (the data behind "
                  "the link) and from Horizon.", "",
                  "| Step | Action | tx | stellar.expert | Horizon | successful |", "|---|---|---|---|---|---|"]
        for c in link_checks:
            lines.append(f"| {c['step']} | {c['action']} | [`{c['tx'][:16]}…`]({EXPERT}/tx/{c['tx']}) | "
                         f"{c['stellar_expert']} | {c['horizon']} | {c['successful']} |")
        dead = [c for c in link_checks if c["stellar_expert"] != 200 or c["horizon"] != 200]
        lines += ["", f"{len(link_checks) - len(dead)} / {len(link_checks)} transaction links resolve."]
        out = self.run_dir / "EVIDENCE.md"
        out.write_text(self.ev.scrub("\n".join(lines)) + "\n", encoding="utf-8")
        return out

    def run(self) -> int:
        print(f"run {self.run_id} -> {self.run_dir}", flush=True)
        self.step(0, self.s0_preflight)
        self.step(1, self.s1_submit_and_lock)
        self.step(2, self.s2_audit_verdict_mint_settle, needs=("safe_request_id",))
        self.step(3, self.s3_agent_checks, needs=("safe_hash",))
        self.step(4, self.s4_buy, needs=("agent", "safe_hash"))
        self.step(5, self.s5_second_call, needs=("agent", "licensed"))
        self.step(6, self.s6_poisoned)
        self.step(7, self.s7_slash, needs=("poison_id",))
        checks = self.verify_links()
        (self.run_dir / "link-check.json").write_text(json.dumps(checks, indent=2) + "\n")
        out = self.render(checks)
        green = sum(1 for k in range(1, 8) if self.ev.steps.get(k, {}).get("status") == "GREEN")
        print(f"\n{green}/7 steps GREEN. Evidence: {out}", flush=True)
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", default=str(REPO / ".env"))
    parser.add_argument("--out", default=str(HERE / "runs"))
    parser.add_argument("--dashboard-url", default=None,
                        help="dashboard base URL; no public one is documented, so a local "
                             "`pnpm dev` against the live API is marked PARTIAL, not GREEN")
    return Rehearsal(parser.parse_args()).run()


if __name__ == "__main__":
    sys.exit(main())
