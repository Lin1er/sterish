"""End-to-end proof of the paid path on testnet, checked from outside the API (STE-42).

Real money moves: a fresh agent is created and funded with testnet USDC, buys a
licence through `demo/x402-buyer/buy.js` (the real x402 client), and every claim
is then verified against the ledger rather than against what the API said.

Run from `api/` with the repo `.env` loaded, against any deployment:

    set -a && . ../.env && set +a
    uv run python scripts/e2e_paid_path.py --api http://127.0.0.1:8765 \
        --out ../docs/evidence/e2e-paid-path.json

What it proves, in order:

1. Nothing undeliverable is priced: every SAFE skill in the registry answers /use
   with either 402 (for sale) or 404 ARTIFACT_NOT_FOUND with no challenge. Anything
   else fails the run.
2. A DANGEROUS version is 403 with no challenge.
3. A fresh agent buys the target skill WITHOUT sending X-AGENT-ADDRESS, so the API
   has to take the payer from the facilitator's verify. Its USDC balance drops by
   exactly the price and `has_license` becomes true on chain.
4. The bytes served hash to the on-chain content_hash.
4b. STE-48: the holder's address alone, a proof signed by another key, a replayed proof,
   a stranger's proof presented for the holder, and a proof for another version are all
   401 with no artifact and no payment challenge (and, with --expiry-wait, an expired one).
5. The same agent signs a SECOND payment for the licence it now holds; the API must
   serve it as held and its USDC balance must not move.

The agent's secret never leaves this process except as an environment variable to
the buyer subprocess. Only public addresses and transaction hashes are printed.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

import httpx
from stellar_sdk import Asset, Keypair, Network, Server, TransactionBuilder

REPO = Path(__file__).resolve().parents[2]
BUYER = REPO / "demo" / "x402-buyer"
HORIZON = os.getenv("HORIZON_URL", "https://horizon-testnet.stellar.org")
SAC_DECIMALS = Decimal(10) ** 7


class E2EFailure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise E2EFailure(message)
    print(f"  ok   {message}")


def usdc_balance(server: Server, account: str, asset: Asset) -> Decimal:
    for balance in server.accounts().account_id(account).call()["balances"]:
        if balance.get("asset_code") == asset.code and balance.get("asset_issuer") == asset.issuer:
            return Decimal(balance["balance"])
    return Decimal(0)


def fund_agent(server: Server, funder: Keypair, agent: Keypair, asset: Asset, usdc: str) -> str:
    """Create the account, open its USDC trustline and send it USDC in ONE transaction.

    One transaction, signed by both, so there is no half-funded agent to clean up
    and no dependency on friendbot being up.
    """
    source = server.load_account(funder.public_key)
    tx = (
        TransactionBuilder(source, Network.TESTNET_NETWORK_PASSPHRASE, base_fee=1000)
        .append_create_account_op(destination=agent.public_key, starting_balance="3")
        .append_change_trust_op(asset=asset, source=agent.public_key)
        .append_payment_op(destination=agent.public_key, asset=asset, amount=usdc)
        .set_timeout(120)
        .build()
    )
    tx.sign(funder)
    tx.sign(agent)
    return server.submit_transaction(tx)["hash"]


def run_buyer(api: str, agent: Keypair, skill_id: str, version: str, **env: str) -> dict:
    child_env = {
        **os.environ,
        "STERISH_API": api,
        "AGENT_SECRET": agent.secret,
        "SKILL_ID": skill_id,
        "SKILL_VERSION": version,
        **env,
    }
    proc = subprocess.run(
        ["node", "buy.js"], cwd=BUYER, env=child_env, capture_output=True, text=True, timeout=240
    )
    out = proc.stdout + proc.stderr
    # buy.js prints only public data; still, never echo anything that looks like a secret.
    safe = re.sub(r"S[A-Z2-7]{55}", "S<redacted>", out)
    print("\n".join("       | " + line for line in safe.strip().splitlines()))
    if proc.returncode != 0:
        raise E2EFailure(f"buyer exited {proc.returncode}")

    def field(name: str) -> str | None:
        match = re.search(rf"{name}\s+(\S+)", out)
        value = match.group(1) if match else None
        return None if value in (None, "null") else value

    return {
        "licence": field("licence"),
        "mint_tx": field("mint tx"),
        "settle_tx": field("settle tx"),
    }


def sep53_sign(keypair: Keypair, message: str) -> str:
    """SEP-53, as a wallet's signMessage and `stellar message sign` produce it."""
    import base64
    import hashlib

    digest = hashlib.sha256(b"Stellar Signed Message:\n" + message.encode("utf-8")).digest()
    return base64.b64encode(keypair.sign(digest)).decode()


def proof_headers(
    http: httpx.Client, api: str, skill: str, version: str, agent: str, signer: Keypair
) -> tuple[dict, dict]:
    challenge = http.get(f"{api}/use/{skill}/{version}/challenge", params={"agent": agent})
    if challenge.status_code != 200:
        raise E2EFailure(f"challenge endpoint answered {challenge.status_code}: {challenge.text}")
    body = challenge.json()
    headers = {
        "X-AGENT-ADDRESS": agent,
        "X-STERISH-PROOF-NONCE": body["nonce"],
        "X-STERISH-PROOF-SIGNATURE": sep53_sign(signer, body["message"]),
    }
    return headers, body


def content_hash_of_served(body: bytes) -> str:
    sys.path.insert(0, str(REPO / "pipeline" / "src"))
    from sterish_pipeline.content_hash import content_hash

    files = json.loads(body)
    return content_hash({name: text.encode("utf-8") for name, text in files.items()})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--skill", default="org.stellar.skills.agentic-payments.x402")
    parser.add_argument("--version", default="2026.8.31")
    parser.add_argument("--dangerous", default="com.fixtures.poisoned.token-drainer@1.0.0")
    parser.add_argument("--funder-env", default="AUDITOR_SECRET")
    parser.add_argument("--out", default=None)
    parser.add_argument(
        "--expiry-wait", action="store_true",
        help="also wait out one challenge and prove an expired proof is refused "
        "(takes STERISH_PROOF_TTL_SECONDS of the target API)",
    )
    args = parser.parse_args()

    api = args.api.rstrip("/")
    horizon = Server(HORIZON)
    asset = Asset(os.getenv("USDC_ASSET_CODE", "USDC"), os.environ["USDC_CLASSIC_ISSUER"])
    funder = Keypair.from_secret(os.environ[args.funder_env])
    http = httpx.Client(timeout=120)
    evidence: dict = {
        "api": api,
        "started_at": int(time.time()),
        "skill": args.skill,
        "version": args.version,
    }

    print(f"API {api}")
    print(f"funder {funder.public_key}\n")

    # --- 1. nothing undeliverable is priced ---------------------------------------
    print("1. every SAFE skill is either for sale (402) or not offered (404, no challenge)")
    rows = http.get(f"{api}/skills", params={"limit": 100}).json()["skills"]
    safe_rows = [r for r in rows if r.get("latest_audited_is_verified")]
    for_sale, not_offered = [], []
    for row in safe_rows:
        sid, ver = row["skill_id"], row["latest_audited_version"]
        r = http.get(f"{api}/use/{sid}/{ver}")
        if r.status_code == 402:
            check("PAYMENT-REQUIRED" in r.headers, f"{sid}@{ver} 402 carries a challenge")
            for_sale.append(f"{sid}@{ver}")
        elif r.status_code == 404:
            check(
                r.json()["error"] == "ARTIFACT_NOT_FOUND", f"{sid}@{ver} 404 is ARTIFACT_NOT_FOUND"
            )
            check("PAYMENT-REQUIRED" not in r.headers, f"{sid}@{ver} 404 carries no challenge")
            not_offered.append(f"{sid}@{ver}")
        else:
            raise E2EFailure(f"{sid}@{ver} answered {r.status_code}: {r.text[:200]}")
    check(f"{args.skill}@{args.version}" in for_sale, "the target skill is for sale")
    evidence["for_sale"], evidence["not_offered"] = for_sale, not_offered
    print(f"  {len(for_sale)} for sale, {len(not_offered)} not offered\n")

    # --- 2. dangerous -------------------------------------------------------------------
    print("2. a DANGEROUS version is never offered")
    d_id, d_ver = args.dangerous.split("@")
    r = http.get(f"{api}/use/{d_id}/{d_ver}")
    check(
        r.status_code == 403 and "PAYMENT-REQUIRED" not in r.headers,
        f"{args.dangerous} -> 403 with no challenge",
    )
    print()

    # --- 3. fresh agent pays without the hint ------------------------------------------
    print("3. a fresh agent pays WITHOUT X-AGENT-ADDRESS")
    agent = Keypair.random()
    evidence["agent"] = agent.public_key
    evidence["funding_tx"] = fund_agent(horizon, funder, agent, asset, "0.2")
    print(f"  agent {agent.public_key} funded: {evidence['funding_tx']}")

    challenge = http.get(f"{api}/use/{args.skill}/{args.version}")
    accepts = json.loads(base64.b64decode(challenge.headers["PAYMENT-REQUIRED"]))["accepts"][0]
    price = Decimal(accepts["amount"]) / SAC_DECIMALS
    pay_to = accepts["payTo"]
    evidence["price_usdc"] = str(price)
    evidence["pay_to"] = pay_to

    before_agent = usdc_balance(horizon, agent.public_key, asset)
    before_pay_to = usdc_balance(horizon, pay_to, asset)
    check(before_agent == Decimal("0.2"), "agent starts with 0.2 USDC")

    licence = http.get(
        f"{api}/license/{args.skill}/{args.version}", params={"agent": agent.public_key}
    ).json()
    check(licence["held"] is False, "agent holds no licence before paying")

    bought = run_buyer(api, agent, args.skill, args.version, AGENT_HEADER="0")
    check(bought["licence"] == "minted", "paid request minted a licence")
    check(bool(bought["mint_tx"]) and bool(bought["settle_tx"]), "mint and settlement tx returned")
    evidence["settle_tx"], evidence["mint_tx"] = bought["settle_tx"], bought["mint_tx"]

    time.sleep(6)  # Horizon ingests a closed ledger a few seconds after RPC confirms it
    after_agent = usdc_balance(horizon, agent.public_key, asset)
    after_pay_to = usdc_balance(horizon, pay_to, asset)
    check(before_agent - after_agent == price, f"agent paid exactly {price} USDC")
    check(after_pay_to - before_pay_to >= price, f"payTo received at least {price} USDC")

    licence = http.get(
        f"{api}/license/{args.skill}/{args.version}", params={"agent": agent.public_key}
    ).json()
    check(licence["held"] is True, "has_license is true on chain")

    # --- 4. the bytes -------------------------------------------------------------------
    print("\n4. the bytes served are the bytes the registry pinned")
    use_url = f"{api}/use/{args.skill}/{args.version}"
    proven, _ = proof_headers(http, api, args.skill, args.version, agent.public_key, agent)
    served = http.get(use_url, headers=proven)
    check(
        served.status_code == 200 and served.headers["X-STERISH-LICENSE"] == "held",
        "licence holder served without payment, with a SEP-53 ownership proof",
    )
    onchain = http.get(f"{api}/check/{args.skill}/{args.version}").json()["content_hash"]
    check(
        content_hash_of_served(served.content) == onchain,
        "content_hash(served bytes) == on-chain content_hash",
    )
    evidence["content_hash"] = onchain

    # --- 4b. the licence cannot be borrowed (STE-48) ------------------------------------
    print("\n4b. naming the holder is not enough: every forged or reused proof is refused")
    stranger = Keypair.random()
    evidence["stranger"] = stranger.public_key

    def refused(response: httpx.Response, code: str, what: str) -> None:
        body = response.json() if response.headers.get("content-type", "").startswith(
            "application/json"
        ) else {}
        check(
            response.status_code == 401
            and body.get("error") == code
            and "PAYMENT-REQUIRED" not in response.headers
            and "X-STERISH-LICENSE" not in response.headers,
            f"{what} -> 401 {code}, no artifact, no payment challenge",
        )

    refused(
        http.get(use_url, headers={"X-AGENT-ADDRESS": agent.public_key}),
        "OWNERSHIP_PROOF_REQUIRED", "holder's address only",
    )
    refused(
        http.get(use_url, params={"agent": agent.public_key}),
        "OWNERSHIP_PROOF_REQUIRED", "holder's address as ?agent=",
    )
    forged, _ = proof_headers(http, api, args.skill, args.version, agent.public_key, stranger)
    refused(http.get(use_url, headers=forged), "INVALID_OWNERSHIP_PROOF",
            "holder's challenge signed by another key")
    refused(http.get(use_url, headers=proven), "INVALID_OWNERSHIP_PROOF",
            "the proof that was already used, replayed")
    own, _ = proof_headers(http, api, args.skill, args.version, stranger.public_key, stranger)
    refused(http.get(use_url, headers=dict(own, **{"X-AGENT-ADDRESS": agent.public_key})),
            "INVALID_OWNERSHIP_PROOF", "a stranger's valid proof presented for the holder")
    other_version, _ = proof_headers(
        http, api, args.skill, args.version + ".other", agent.public_key, agent
    )
    refused(http.get(use_url, headers=other_version), "INVALID_OWNERSHIP_PROOF",
            "a proof for another version")
    stranger_paying = http.get(use_url, headers=own)
    check(stranger_paying.status_code == 402 and "PAYMENT-REQUIRED" in stranger_paying.headers,
          "a stranger proving its OWN address, with no licence, is asked to pay (402)")

    if args.expiry_wait:
        pending, challenge = proof_headers(
            http, api, args.skill, args.version, agent.public_key, agent
        )
        wait = max(0, challenge["expires_at"] - int(time.time())) + 3
        print(f"       waiting {wait}s for the challenge to expire")
        time.sleep(wait)
        refused(http.get(use_url, headers=pending), "INVALID_OWNERSHIP_PROOF",
                "a correctly signed proof after its challenge expired")
    evidence["ownership_proof"] = "held with proof 200; address-only, forged, replayed, " \
        "borrowed, wrong-version" + (", expired" if args.expiry_wait else "") + " all 401"

    # --- 5. a second payment for a held licence is not charged ---------------------------
    print("\n5. a second signed payment for a licence already held is not charged")
    second = run_buyer(
        api, agent, args.skill, args.version, AGENT_HEADER="0", EXPECT_LICENSE="held"
    )
    check(second["settle_tx"] is None, "no settlement for the second payment")
    time.sleep(6)
    check(
        usdc_balance(horizon, agent.public_key, asset) == after_agent,
        "agent balance unchanged by the second payment",
    )

    evidence["finished_at"] = int(time.time())
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
