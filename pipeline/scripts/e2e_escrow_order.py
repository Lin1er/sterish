"""End-to-end proof of the STE-49 escrow order on testnet, through the orchestrator.

Real USDC moves on the live stack (Escrow v1 + Registry/Tokens v2). Two runs, both with
`escrow_lock="before_audit"`:

1. SAFE skill: `open_escrow_job` locks fee + bond **before the skill is even registered
   or audited** (read back: request Bonded, escrow holds fee+bond, registry has no
   record of the hash yet). Then the audit runs, and `orchestrate` registers, submits,
   mints and **settles the same request_id**, found through the journal.
2. Poisoned skill: same lock, audit comes back DANGEROUS, and `orchestrate` **slashes
   the bond to the configured reporter**: reporter +bond, developer's fee refunded,
   auditor -bond.

Every claim is read back from the chain (escrow `get_request`, SAC balances, registry),
not taken from the orchestrator's own step list. Skill ids come from
`new_test_skill_id("e2e", ...)`, so nothing reaches the dashboard's default listing.

    cd pipeline && set -a && . ../.env && set +a
    uv run --project . python scripts/e2e_escrow_order.py --out ../docs/evidence/ste-49-e2e.json

Only public addresses and transaction hashes are printed or written.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from stellar_sdk import Address, scval

from sterish_pipeline import onchain, orchestrator
from sterish_pipeline.audit import run_audit
from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.namespaces import new_test_skill_id
from sterish_pipeline.orchestrator import OrchestratorConfig, Step

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "docs" / "rehearsal" / "skills"
REGISTRY = "CCZJN366SV57JEBZVXGYY3ZBLJNFV4IR5ILCAI3EMX2WDNQPEPQ4BRL2"
TOKENS = "CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T"
ESCROW = "CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE"
USDC_SAC = "CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA"
FEE = 1_000_000      # 0.1 USDC
BOND = 2_000_000     # 0.2 USDC


class E2EFailure(Exception):
    pass


checks: list[dict] = []


def check(condition: bool, message: str) -> None:
    checks.append({"check": message, "ok": bool(condition)})
    if not condition:
        raise E2EFailure(message)
    print(f"  ok   {message}")


def balance(cfg: PipelineConfig, address: str) -> int:
    return int(onchain.simulate(cfg, USDC_SAC, "balance", [scval.to_address(Address(address))])
               or 0)


def request(cfg: PipelineConfig, request_id: int) -> dict:
    return onchain.simulate(cfg, ESCROW, "get_request", [scval.to_uint32(request_id)])


def status(record: dict) -> str:
    s = record.get("status")
    return str(s[0] if isinstance(s, (list, tuple)) and s else s)


def prepare(kind: str, slug: str, workdir: Path) -> tuple[Path, str]:
    skill_id = new_test_skill_id("e2e", slug)
    target = workdir / kind
    shutil.copytree(SKILLS / kind, target)
    manifest = json.loads((target / "manifest.json").read_text())
    manifest["skill_id"] = skill_id
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return target, skill_id


def run(kind: str, slug: str, expect: str, cfg: PipelineConfig, env: dict, workdir: Path,
        evidence: dict) -> None:
    skill_dir, skill_id = prepare(kind, slug, workdir)
    version = json.loads((skill_dir / "manifest.json").read_text()).get("version", "1.0.0")
    developer, auditor, reporter = (env["DEVELOPER_ADDRESS"], env["AUDITOR_ADDRESS"],
                                    env["REPORTER_ADDRESS"])
    config = OrchestratorConfig(
        registry_id=REGISTRY, tokens_id=TOKENS, escrow_id=ESCROW,
        owner_secret=env["DEVELOPER_SECRET"], auditor_secret=env["AUDITOR_SECRET"],
        admin_secret=env["DEPLOYER_SECRET"], reports_dir=workdir / "reports",
        journal_path=workdir / f"journal-{kind}.json", fee_amount=FEE, bond_amount=BOND,
        run_escrow=True, escrow_lock="before_audit", reporter_address=reporter,
    )
    record: dict = {"skill_id": skill_id, "version": version, "expect": expect}
    evidence["runs"].append(record)
    parties = {"developer": developer, "auditor": auditor, "reporter": reporter,
               "escrow": ESCROW}
    before = {k: balance(cfg, a) for k, a in parties.items()}

    print(f"\n{kind}: {skill_id}@{version}")
    # 1. lock, before registration and before the audit exists
    opened = orchestrator.open_escrow_job(skill_id, version, config, cfg)
    record["open"] = [s.to_dict() for s in opened]
    request_id = next(s.value for s in opened if s.step == Step.CREATE_REQUEST)
    record["request_id"] = request_id
    check(isinstance(request_id, int), f"create_audit_request returned request #{request_id}")
    locked = request(cfg, request_id)
    time.sleep(2)
    after_lock = {k: balance(cfg, a) for k, a in parties.items()}
    lock_delta = {k: after_lock[k] - before[k] for k in parties}
    check(status(locked) == "Bonded" and locked["skill_id"] == skill_id,
          f"request #{request_id} is Bonded for {skill_id} before the audit")
    check(lock_delta == {"developer": -FEE, "auditor": -BOND, "reporter": 0,
                         "escrow": FEE + BOND},
          f"lock moved fee and bond into escrow: {lock_delta}")

    run_result = run_audit(skill_dir, config=cfg, skip_sandbox=True)
    run_result.validate(submittable=True)
    document = run_result.verdict_json()
    check(onchain.lookup_by_hash(cfg, REGISTRY, document["content_hash"]) is None,
          "the registry has no record of these bytes while the funds are already locked")
    check(document["verdict"] == expect, f"audit verdict {document['verdict']} == {expect}")

    # 2. the audit result closes the same job
    result = orchestrator.orchestrate(document, config, cfg)
    record["orchestrate"] = result.to_dict()
    check(result.ok, "orchestrate reported every step done or skipped")
    closed = request(cfg, request_id)
    time.sleep(2)
    after = {k: balance(cfg, a) for k, a in parties.items()}
    net = {k: after[k] - before[k] for k in parties}
    record["balance_deltas"] = net
    record["final_status"] = status(closed)
    if expect == "SAFE":
        check(status(closed) == "Settled", f"request #{request_id} Settled")
        check(net == {"developer": -FEE, "auditor": FEE, "reporter": 0, "escrow": 0},
              f"settle paid fee+bond to the auditor: net {net}")
        check(onchain.is_verified(cfg, REGISTRY, skill_id, version),
              "registry.is_verified true for the audited version")
    else:
        check(status(closed) == "Slashed", f"request #{request_id} Slashed")
        check(net == {"developer": 0, "auditor": -BOND, "reporter": BOND, "escrow": 0},
              f"slash sent the bond to the reporter and refunded the fee: net {net}")
        slash = next(s for s in result.steps if s.step == Step.SLASH)
        check(reporter in slash.detail, "the slash step names the reporter it paid")
    record["tx"] = result.tx_hashes() | {
        str(s.step): s.tx_hash for s in opened if s.tx_hash
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    env = {k: os.environ[k] for k in (
        "DEVELOPER_ADDRESS", "DEVELOPER_SECRET", "AUDITOR_ADDRESS", "AUDITOR_SECRET",
        "DEPLOYER_SECRET", "REPORTER_ADDRESS")}
    cfg = PipelineConfig(registry_contract_id=REGISTRY, use_llm=False)
    evidence = {"ticket": "STE-49", "started_at": int(time.time()), "escrow": ESCROW,
                "registry": REGISTRY, "tokens": TOKENS, "fee": FEE, "bond": BOND,
                "reporter": env["REPORTER_ADDRESS"], "runs": []}
    workdir = Path(tempfile.mkdtemp(prefix="ste49-"))
    try:
        run("safe", "escrow-order-safe", "SAFE", cfg, env, workdir, evidence)
        run("poisoned", "escrow-order-poisoned", "DANGEROUS", cfg, env, workdir, evidence)
        evidence["result"] = "pass"
        print("\nPASS")
        return 0
    except E2EFailure as exc:
        evidence["result"] = f"fail: {exc}"
        print(f"\nFAIL: {exc}")
        return 1
    finally:
        evidence["checks"] = checks
        evidence["finished_at"] = int(time.time())
        if args.out:
            Path(args.out).write_text(json.dumps(evidence, indent=2) + "\n")
            print(f"evidence written to {args.out}")


if __name__ == "__main__":
    sys.exit(main())
