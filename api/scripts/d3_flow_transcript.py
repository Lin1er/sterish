"""Walk the whole Sterish flow against a live API and write it down as evidence (STE-52).

SOW Deliverable 3 asks for proof of the full flow: register -> audit -> license -> use.
This script produces that proof from the API a client actually uses, as a Markdown
transcript of real requests and responses, and **checks every claim it writes** instead
of just printing it:

1. the deployment is up and reads the expected registry;
2. register + audit: the version's registration and audit transactions (from `/check`),
   the published report, and `sha256(report) == evidence_hash` on chain;
3. license: an unpaid request is 402 with a decoded x402 challenge; a fresh agent,
   funded here, pays through the real x402 client (`demo/x402-buyer/buy.js`), the USDC
   balance drops by exactly the price, and a licence is minted to the payer;
4. use: the served bytes hash to the on-chain `content_hash`; `/license` says held; the
   repeat call is free — with an ownership proof when the deployment requires one
   (STE-48), without when it does not yet;
5. the negative path: a DANGEROUS version is 403 with no challenge.

Real money moves (testnet USDC, the price of one licence). The agent's secret stays in this
process and the buyer subprocess's environment; only public addresses and transaction
hashes are written.

    cd api && set -a && . ../.env && set +a
    uv run python scripts/d3_flow_transcript.py --api https://api-sterish.jameshub.fun \\
        --out ../docs/evidence/d3-flow-transcript-<date>.md
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
from stellar_sdk import Asset, Keypair, Server

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_paid_path import (  # noqa: E402
    HORIZON,
    REPO,
    E2EFailure,
    content_hash_of_served,
    fund_agent,
    proof_headers,
    run_buyer,
    usdc_balance,
)

EXPERT = "https://stellar.expert/explorer/testnet"
UA = {"User-Agent": "sterish-d3-transcript/1.0"}


class Transcript:
    def __init__(self, api: str):
        self.api = api
        self.lines: list[str] = []
        self.checks: list[tuple[bool, str]] = []

    def h(self, text: str) -> None:
        self.lines += ["", text, ""]

    def _gap(self) -> None:
        # Markdown needs a blank line between a bullet list and a following table or
        # paragraph, or the table renders as part of the last bullet.
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def p(self, text: str) -> None:
        self._gap()
        self.lines += [text, ""]

    def request(self, method: str, path: str, headers: dict | None = None,
                response: httpx.Response | None = None, body: str | None = None,
                note: str | None = None) -> None:
        self._gap()
        shown = {k: v for k, v in (headers or {}).items() if k.lower() != "user-agent"}
        hdrs = "".join(f" \\\n  -H '{k}: {v}'" for k, v in shown.items())
        self.lines += ["```bash", f"curl -s{' -X ' + method if method != 'GET' else ''} "
                       f"'{self.api}{path}'{hdrs}", "```"]
        if response is not None:
            keep = [k for k in response.headers if k.lower().startswith(("x-sterish", "payment-",
                                                                        "x-payment"))]
            head = [f"HTTP {response.status_code}"] + [f"{k}: {response.headers[k][:120]}"
                                                       for k in keep]
            self.lines += ["```http", *head, "```"]
        if body is not None:
            self.lines += ["```json", body, "```"]
        if note:
            self.lines += [note]
        self.lines.append("")

    def check(self, ok: bool, text: str) -> None:
        self.checks.append((ok, text))
        self.lines.append(f"- {'✅' if ok else '❌'} {text}")
        print(f"  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            raise E2EFailure(text)

    def tx(self, tx_hash: str | None) -> str:
        return f"[`{tx_hash[:16]}…`]({EXPERT}/tx/{tx_hash})" if tx_hash else "_not recorded_"


def pretty(data, limit: int = 60) -> str:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    lines = text.splitlines()
    return "\n".join(lines[:limit] + (["  …"] if len(lines) > limit else []))


def badge_tx_from_evidence(skill_id: str, version: str) -> str | None:
    """The mint_verified tx, when a committed run log recorded it. Not guessed otherwise."""
    for path in sorted((REPO / "docs" / "evidence").glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        rows = data if isinstance(data, list) else data.get("rows") or data.get("runs") or []
        for row in rows if isinstance(rows, list) else []:
            if (isinstance(row, dict) and row.get("skill_id") == skill_id
                    and row.get("version") == version):
                tx = (row.get("tx") or {}).get("mint_verified")
                if tx:
                    return tx
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--skill", default="org.stellar.skills.cross-chain.cctp")
    parser.add_argument("--version", default="2026.8.31")
    parser.add_argument("--dangerous", default="com.fixtures.poisoned.token-drainer@1.0.0")
    parser.add_argument("--funder-env", default="AUDITOR_SECRET")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    api = args.api.rstrip("/")
    http = httpx.Client(timeout=120, headers=UA)
    horizon = Server(HORIZON)
    asset = Asset(os.getenv("USDC_ASSET_CODE", "USDC"), os.environ["USDC_CLASSIC_ISSUER"])
    funder = Keypair.from_secret(os.environ[args.funder_env])
    t = Transcript(api)
    sid, ver = args.skill, args.version
    started = datetime.now(UTC).replace(microsecond=0)

    t.lines += [
        "# Sterish full flow, recorded from the live API",
        "",
        f"> Generated by `api/scripts/d3_flow_transcript.py` on **{started.isoformat()}** against "
        f"`{api}` (STE-52). Every request below was made for real; every ✅ is a check the script "
        "ran, and the script stops at the first ❌. Testnet only — links expire with the testnet "
        "reset on 16 December 2026.",
        "",
        f"Skill followed: **`{sid}` {ver}** · negative path: **`{args.dangerous}`**",
    ]
    try:
        # --- 0. the deployment ---------------------------------------------------
        t.h("## 0. The deployment answers, and reads the registry it claims")
        r = http.get(f"{api}/health")
        health = r.json()
        t.request("GET", "/health", response=r, body=pretty(health))
        t.check(r.status_code == 200 and health.get("rpc_reachable") is True,
                "`/health` is 200 with the Soroban RPC reachable")
        registry = health.get("registry_contract_id")
        t.p(f"Registry: [`{registry}`]({EXPERT}/contract/{registry})")

        r = http.get(f"{api}/skills", params={"limit": 100})
        listing = r.json()
        summary = {k: listing[k] for k in ("total", "chain_total", "hidden_test_entries")}
        summary["verdicts"] = {}
        for row in listing["skills"]:
            v = row["latest_audited_verdict"] or "UNAUDITED"
            summary["verdicts"][v] = summary["verdicts"].get(v, 0) + 1
        t.request("GET", "/skills?limit=100", response=r, body=pretty(summary),
                  note=f"_Summarised from the {len(listing['skills'])} rows returned._")
        t.check(any(x["skill_id"] == sid for x in listing["skills"]),
                f"`{sid}` is in the public registry listing")

        # --- 1. register + audit ---------------------------------------------------
        t.h("## 1. Register → audit: the verdict is on chain, and so is the hash of its report")
        r = http.get(f"{api}/check/{sid}/{ver}")
        record = r.json()
        t.request("GET", f"/check/{sid}/{ver}", response=r, body=pretty(record))
        ev = record["evidence"]
        t.check(r.status_code == 200 and record["verdict"] == "SAFE" and record["is_verified"],
                f"verdict **SAFE** ({record['trust_score']}/100), VERIFIED on chain")
        t.check(bool(ev.get("registration_tx")) and bool(ev.get("audit_tx")),
                "registration and audit transactions are linked")
        badge = badge_tx_from_evidence(sid, ver)
        t.p("| Step | Transaction |\n|---|---|\n"
            f"| `register_skill` | {t.tx(ev.get('registration_tx'))} |\n"
            f"| `submit_verdict` | {t.tx(ev.get('audit_tx'))} |\n"
            f"| `mint_verified` (badge) | {t.tx(badge)} |")

        r = http.get(f"{api}/reports/{sid}/{ver}")
        served_hash = hashlib.sha256(r.content).hexdigest()
        report = r.json()
        t.request("GET", f"/reports/{sid}/{ver}", response=r,
                  body=pretty({k: report[k] for k in ("skill_id", "version", "verdict", "score",
                                                     "risk", "recommendation", "findings")}),
                  note="_Trimmed to the verdict fields; the hash below is over the full bytes._")
        t.check(served_hash == ev["evidence_hash"],
                f"`sha256(report bytes)` = `{served_hash[:16]}…` = on-chain `evidence_hash`")

        # --- 2. license ----------------------------------------------------------------
        t.h("## 2. License: 402 → pay USDC over x402 → licence minted")
        r = http.get(f"{api}/use/{sid}/{ver}")
        challenge = json.loads(base64.b64decode(r.headers.get("PAYMENT-REQUIRED", "")) or "{}")
        t.request("GET", f"/use/{sid}/{ver}", response=r, body=pretty(challenge),
                  note="_The `PAYMENT-REQUIRED` header, base64-decoded._")
        accepts = (challenge.get("accepts") or [{}])[0]
        t.check(r.status_code == 402 and accepts.get("scheme") == "exact",
                f"402 with an x402 `exact` challenge on `{accepts.get('network')}`")
        price = Decimal(accepts["amount"]) / Decimal(10) ** 7
        t.check(accepts.get("asset") and accepts.get("payTo", "").startswith("G"),
                f"price **{price} USDC** (SAC `{accepts['asset'][:8]}…`), paid to "
                f"`{accepts['payTo'][:8]}…`")

        agent = Keypair.random()
        funding = fund_agent(horizon, funder, agent, asset, "0.5")
        t.p(f"A fresh agent `{agent.public_key}` is created and funded with 0.5 USDC "
            f"({t.tx(funding)}). It holds no XLM beyond the account reserve: the facilitator "
            "sponsors fees.")
        time.sleep(6)
        before = usdc_balance(horizon, agent.public_key, asset)
        print("  buying through demo/x402-buyer/buy.js")
        bought = run_buyer(api, agent, sid, ver, AGENT_HEADER="0", STOP_AFTER_PAYMENT="1")
        time.sleep(6)
        after = usdc_balance(horizon, agent.public_key, asset)
        t.p("The agent signs the payment with the reference x402 client "
            "(`@x402/fetch` + `@x402/stellar`, in `demo/x402-buyer/buy.js`) and retries "
            "**without naming itself**: the API takes the payer from the facilitator's verify.")
        t._gap()
        t.lines += ["```http", "HTTP 200", f"X-STERISH-LICENSE: {bought['licence']}",
                    f"X-STERISH-SETTLEMENT-TX: {bought['settle_tx']}",
                    f"X-STERISH-LICENSE-TX: {bought['mint_tx']}", "```", ""]
        t.check(bought["licence"] == "minted" and bought["settle_tx"] and bought["mint_tx"],
                "paid request answered 200 with a minted licence")
        t.check(before - after == price, f"agent USDC balance fell by exactly {price}")
        t.p("| Step | Transaction |\n|---|---|\n"
            f"| x402 settlement (USDC transfer) | {t.tx(bought['settle_tx'])} |\n"
            f"| `mint_license` (soulbound) | {t.tx(bought['mint_tx'])} |")

        r = http.get(f"{api}/license/{sid}/{ver}", params={"agent": agent.public_key})
        t.request("GET", f"/license/{sid}/{ver}?agent={agent.public_key}", response=r,
                  body=pretty(r.json()))
        t.check(r.json().get("held") is True, "`has_license` is true on the tokens contract")

        # --- 3. use ----------------------------------------------------------------------
        t.h("## 3. Use: the bytes served are the bytes that were audited, and the repeat is free")
        probe = http.get(f"{api}/use/{sid}/{ver}/challenge", params={"agent": agent.public_key})
        if probe.status_code == 200:
            headers, _ = proof_headers(http, api, sid, ver, agent.public_key, agent)
            shown = dict(headers, **{"X-STERISH-PROOF-SIGNATURE": "<SEP-53 signature, base64>"})
            mode = "with a SEP-53 ownership proof (STE-48 is deployed)"
        else:
            headers = {"X-AGENT-ADDRESS": agent.public_key}
            shown = headers
            mode = ("with the agent address only — this deployment predates STE-48, whose "
                    "ownership proof is merged but not yet deployed")
        r = http.get(f"{api}/use/{sid}/{ver}", headers=headers)
        onchain_hash = record["content_hash"]
        served = content_hash_of_served(r.content) if r.status_code == 200 else None
        t.request("GET", f"/use/{sid}/{ver}", headers=shown, response=r,
                  note=f"_Repeat request {mode}. Body: the skill's files, "
                       f"{len(r.content)} bytes._")
        t.check(r.status_code == 200 and r.headers.get("X-STERISH-LICENSE") == "held",
                "repeat call served from the held licence, no payment asked")
        t.check(served == onchain_hash,
                f"`content_hash(served files)` = `{onchain_hash[:16]}…` = on-chain `content_hash`")
        time.sleep(6)
        t.check(usdc_balance(horizon, agent.public_key, asset) == after,
                "agent balance unchanged by the repeat call")

        # --- 4. negative path ----------------------------------------------------------
        t.h("## 4. The negative path: a poisoned skill is flagged and cannot be bought")
        d_id, d_ver = args.dangerous.split("@")
        r = http.get(f"{api}/check/{d_id}/{d_ver}")
        dangerous = r.json()
        t.request("GET", f"/check/{d_id}/{d_ver}", response=r,
                  body=pretty({k: dangerous[k] for k in ("skill_id", "version", "verdict",
                                                        "trust_score", "is_verified")}))
        t.check(dangerous["verdict"] == "DANGEROUS" and not dangerous["is_verified"],
                f"`{d_id}` is **DANGEROUS** ({dangerous['trust_score']}/100), not VERIFIED")
        r = http.get(f"{api}/use/{d_id}/{d_ver}")
        t.request("GET", f"/use/{d_id}/{d_ver}", response=r, body=pretty(r.json()))
        t.check(r.status_code == 403 and "PAYMENT-REQUIRED" not in r.headers,
                "403, and no payment challenge: it is never offered for sale")

        t.h("## Result")
        t.p(f"**PASS** — {len(t.checks)} checks, all against the live deployment "
            f"and the ledger. Agent `{agent.public_key}`.")
        code = 0
        print("\nPASS")
    except E2EFailure as exc:
        t.h("## Result")
        t.p(f"**FAIL** at: {exc}")
        print(f"\nFAIL: {exc}")
        code = 1

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(t.lines).strip() + "\n", encoding="utf-8")
    print(f"transcript written to {args.out}")
    return code


if __name__ == "__main__":
    sys.exit(main())
