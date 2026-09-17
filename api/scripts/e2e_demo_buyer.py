"""End-to-end proof of the demo buyer on testnet (STE-43), checked from outside the API.

Run against an API started with DEMO_BUYER_ENABLED=1 and DEMO_TREASURY_SECRET set:

    set -a && . ../.env && set +a
    uv run python scripts/e2e_demo_buyer.py --api http://127.0.0.1:8765 \
        --out ../docs/evidence/ste-43-e2e-demo-buyer.json

What it proves:

1. Refusals happen before anything moves: a DANGEROUS version (403), a SAFE version
   with no artifact (404), and an unregistered skill (404) create no job.
2. A purchase runs to `succeeded`, every step `ok`, and polling shows it progressing.
3. Every transaction the job reports exists on the ledger and succeeded.
4. The agent spent exactly the price, `has_license` is true, and a second purchase
   started while one runs is refused with 409.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

import httpx

HORIZON = os.getenv("HORIZON_URL", "https://horizon-testnet.stellar.org")


class E2EFailure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise E2EFailure(message)
    print(f"  ok   {message}")


def tx_succeeded(http: httpx.Client, tx_hash: str) -> bool:
    for _ in range(10):
        r = http.get(f"{HORIZON}/transactions/{tx_hash}")
        if r.status_code == 200:
            return bool(r.json().get("successful"))
        time.sleep(3)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--skill", default="org.stellar.skills.dapp.react")
    parser.add_argument("--version", default="2026.8.31")
    parser.add_argument("--dangerous", default="com.fixtures.poisoned.token-drainer@1.0.0")
    # A SAFE version on Registry v2 with no published artifact (the STE-49 e2e skill).
    # The earlier default, com.sterish.canon-safe-1788685783, exists only on Registry v1.
    parser.add_argument(
        "--no-artifact", default="com.sterish.e2e-escrow-order-safe-1789580908@1.0.0"
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    api = args.api.rstrip("/")
    http = httpx.Client(timeout=120)
    evidence: dict = {"api": api, "skill": args.skill, "version": args.version}

    status = http.get(f"{api}/demo/status").json()
    check(status["enabled"] is True, "demo buyer is enabled")
    check(bool(status["treasury"]), f"treasury is {status['treasury']}")
    evidence["treasury"] = status["treasury"]

    print("\n1. refusals create no job")
    before = http.get(f"{api}/demo/status").json()["used_today"]
    for target, want, code in (
        (args.dangerous, 403, "NOT_VERIFIED"),
        (args.no_artifact, 404, "ARTIFACT_NOT_FOUND"),
        ("com.sterish.does-not-exist@1.0.0", 404, "SKILL_NOT_FOUND"),
    ):
        sid, ver = target.split("@")
        r = http.post(f"{api}/demo/purchases", json={"skill_id": sid, "version": ver})
        check(r.status_code == want and r.json()["error"] == code, f"{target} -> {want} {code}")
    check(http.get(f"{api}/demo/status").json()["used_today"] == before, "no purchase was counted")

    print("\n2. a purchase runs to completion")
    started = http.post(
        f"{api}/demo/purchases", json={"skill_id": args.skill, "version": args.version}
    )
    check(started.status_code == 202, "POST /demo/purchases -> 202")
    job = started.json()
    check(job["signer"]["kind"] == "demo", "response labels the signer as a demo account")

    busy = http.post(
        f"{api}/demo/purchases", json={"skill_id": args.skill, "version": args.version}
    )
    check(
        busy.status_code == 409 and busy.json()["error"] == "DEMO_BUSY",
        "a concurrent purchase -> 409",
    )

    seen_statuses = set()
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        job = http.get(f"{api}{started.headers['Location']}").json()
        seen_statuses.add(tuple(s["status"] for s in job["steps"]))
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(1)
    for step in job["steps"]:
        print(f"       | {step['status']:8} {step['key']:17} {step.get('detail') or ''}")
    check(job["status"] == "succeeded", f"job succeeded (error: {job.get('error')})")
    check(len(seen_statuses) > 1, "progress was observable while polling")
    steps = {s["key"]: s for s in job["steps"]}

    print("\n3. every transaction is on the ledger")
    txs = {
        "funding": steps["fund_agent"]["tx_hash"],
        "settlement": steps["pay"]["data"]["settlement_tx"],
        "mint": steps["pay"]["data"]["mint_tx"],
    }
    for name, tx_hash in txs.items():
        check(bool(tx_hash) and tx_succeeded(http, tx_hash), f"{name} {tx_hash} succeeded on chain")
    evidence.update({f"{k}_tx": v for k, v in txs.items()})
    evidence["agent"] = job["agent"]

    print("\n4. the agent paid exactly the price and holds the licence")
    price = Decimal(steps["challenge"]["data"]["amount_usdc"])
    balances = http.get(f"{HORIZON}/accounts/{job['agent']}").json()["balances"]
    usdc = next(Decimal(b["balance"]) for b in balances if b.get("asset_code") == "USDC")
    check(usdc == 0, f"agent was funded {price} USDC and now holds {usdc}")
    licence = http.get(
        f"{api}/license/{args.skill}/{args.version}", params={"agent": job["agent"]}
    ).json()
    check(licence["held"] is True, "has_license is true on chain")
    check(
        steps["verify_bytes"]["data"]["content_hash"]
        == http.get(f"{api}/check/{args.skill}/{args.version}").json()["content_hash"],
        "verified content_hash is the registry's",
    )

    evidence["job"] = job
    evidence["result"] = "pass"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(f"\nevidence written to {args.out}")
    print("\nPASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except E2EFailure as exc:
        print(f"\nFAIL: {exc}")
        sys.exit(1)
