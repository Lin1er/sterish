"""STE-44 — copy the registry's real entries onto the upgradeable v2 contracts.

Upgradeability cannot be added to a live Soroban contract: the contract replaces
its own wasm, so the capability has to be in the bytes that were deployed. That
forces a new address, and a new address starts empty. This script is what makes
it not-empty.

WHAT IS MIGRATED, AND WHAT IS NOT
--------------------------------
Everything that means something: the `org.stellar.skills.*` catalogue, the
`com.fixtures.*` demo data, and every version they carry — read off the OLD
registry rather than rebuilt from a list in this file, so nothing can be
silently left behind by a stale constant.

Not migrated: the `com.sterish.it-*` / `e2e-*` / `canon-*` entries. Those are
test residue (`sterish_pipeline.namespaces.is_test_skill_id`), 47 of the 71
entries, and the registry has no delete — copying them would carry the mess
across for no reason. `com.fixtures.*` is NOT test residue; it is demo data that
is meant to be visible.

ORDER IS PART OF THE DATA
-------------------------
Entries are replayed in the OLD registry's `SkillIndex` order, which is
registration order, so `query_all_skills` pages the same way on the new contract
and the dashboard's ordering does not silently change. Versions are replayed in
their stored order, so `latest_version` lands on the same version it had.

WHAT IS *NOT* CARRIED ACROSS, AND CANNOT BE
-------------------------------------------
`registered_at` and `audited_at` are stamped by the contract from the ledger
clock. A replay happens now, so the new records carry today's timestamps. The
original ones stay readable on the old contract for as long as testnet keeps it
(see docs/deployments.md for the reset date). This is stated rather than hidden:
a migrated record is a faithful copy of the CLAIM, not of when it was made.

Usage:
    set -a && . ./.env && set +a
    export OLD_REGISTRY_CA=C... OLD_TOKENS_CA=C...     # the superseded pair
    uv run --project pipeline python scripts/migrate-registry.py --dry-run
    uv run --project pipeline python scripts/migrate-registry.py
    uv run --project pipeline python scripts/migrate-registry.py --verify-only

REGISTRY_CA / TOKENS_CA are the NEW pair. Re-running is safe: every write checks
the destination first, so an interrupted run resumes instead of double-applying.

No secret is ever printed. Secrets are read from the environment and handed
straight to the signer.
"""

from __future__ import annotations

import os
import re
import sys

from stellar_sdk import scval

from sterish_pipeline import namespaces, onchain
from sterish_pipeline.config import PipelineConfig

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"

# `scval.to_native` hands back an `Address` whose repr wraps the G… we need.
_ADDRESS_RE = re.compile(r"G[A-Z2-7]{55}")


def address_of(value) -> str:
    match = _ADDRESS_RE.search(str(value))
    if not match:
        raise SystemExit(f"could not read an account address out of {value!r}")
    return match.group(0)


def config(registry_id: str) -> PipelineConfig:
    return PipelineConfig(
        registry_contract_id=registry_id,
        rpc_url=os.getenv("STELLAR_RPC_URL", PipelineConfig().rpc_url),
        network_passphrase=os.getenv(
            "STELLAR_NETWORK_PASSPHRASE", PipelineConfig().network_passphrase
        ),
    )


def read_source(cfg: PipelineConfig, registry_id: str, tokens_id: str) -> list[dict]:
    """Every non-test version on the old registry, in registration order."""
    count = onchain.simulate(cfg, registry_id, "get_skill_count")
    rows: list[dict] = []

    for index in range(count):
        page = onchain.simulate(
            cfg, registry_id, "query_all_skills",
            [scval.to_uint32(index), scval.to_uint32(1)],
        )
        if not page:
            continue
        entry = page[0]
        skill_id = entry["skill_id"]
        if namespaces.is_test_skill_id(skill_id):
            continue

        for version in entry["versions"]:
            record = onchain.get_version(cfg, registry_id, skill_id, version)
            verdict = record["verdict"]
            if isinstance(verdict, (list, tuple)) and verdict:
                verdict = verdict[0]
            rows.append({
                "skill_id": skill_id,
                "version": version,
                "owner": address_of(record["owner"]),
                "content_hash": bytes(record["content_hash"]).hex(),
                "verdict": str(verdict),
                "trust_score": int(record["trust_score"]),
                "evidence_hash": bytes(record["evidence_hash"]).hex(),
                "badge": bool(onchain.simulate(
                    cfg, tokens_id, "is_verified_token",
                    [scval.to_string(skill_id), scval.to_string(version)],
                )) if tokens_id else False,
            })
    return rows


def present(cfg: PipelineConfig, registry_id: str, skill_id: str, version: str):
    """The destination's record for this version, or None."""
    try:
        return onchain.get_version(cfg, registry_id, skill_id, version)
    except onchain.ContractCallError:
        return None


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    verify_only = "--verify-only" in argv

    old_registry = os.environ["OLD_REGISTRY_CA"]
    old_tokens = os.environ["OLD_TOKENS_CA"]
    new_registry = os.environ["REGISTRY_CA"]
    new_tokens = os.environ["TOKENS_CA"]
    if old_registry == new_registry:
        raise SystemExit(
            "OLD_REGISTRY_CA == REGISTRY_CA — nothing to migrate. Set the old "
            "pair explicitly; sourcing .env twice shadows them."
        )

    old = config(old_registry)
    new = config(new_registry)

    print(f"source registry {old_registry}")
    print(f"source tokens   {old_tokens}")
    print(f"target registry {new_registry}")
    print(f"target tokens   {new_tokens}")
    print()

    rows = read_source(old, old_registry, old_tokens)
    skills = {row["skill_id"] for row in rows}
    badges = sum(1 for row in rows if row["badge"])
    print(f"{len(rows)} version(s) across {len(skills)} skill(s), {badges} badge(s) to carry")
    print(f"{DIM}test-namespace entries skipped by namespaces.is_test_skill_id{RESET}")
    print()

    if dry_run:
        for row in rows:
            print(f"  {row['skill_id']:52} {row['version']:10} "
                  f"{row['verdict']:10} {row['trust_score']:>3} "
                  f"{'badge' if row['badge'] else '     '}")
        return 0

    developer_secret = os.environ["DEVELOPER_SECRET"]
    auditor_secret = os.environ["AUDITOR_SECRET"]

    failures: list[str] = []
    for row in rows:
        skill_id, version = row["skill_id"], row["version"]
        label = f"{skill_id}@{version}"

        if not verify_only:
            # Each write checks the destination first, so an interrupted run
            # resumes rather than failing on VersionAlreadyExists.
            if present(new, new_registry, skill_id, version) is None:
                onchain.register_skill(
                    new, new_registry, developer_secret,
                    skill_id, version, row["content_hash"],
                )

            record = present(new, new_registry, skill_id, version)
            verdict_now = record["verdict"]
            if isinstance(verdict_now, (list, tuple)) and verdict_now:
                verdict_now = verdict_now[0]
            if row["verdict"] != "Unaudited" and str(verdict_now) != row["verdict"]:
                onchain.submit_verdict(
                    new, new_registry, auditor_secret, skill_id, version,
                    row["verdict"], row["trust_score"], row["evidence_hash"],
                )

            if row["badge"]:
                has = onchain.simulate(
                    new, new_tokens, "is_verified_token",
                    [scval.to_string(skill_id), scval.to_string(version)],
                )
                if not has:
                    onchain.mint_verified(
                        new, new_tokens, auditor_secret,
                        skill_id, version, row["owner"],
                    )

        # Verification reads from the CHAIN, never from what we just sent. The
        # whole point of the exercise is that the new contract holds the data,
        # not that this script believes it does.
        landed = present(new, new_registry, skill_id, version)
        if landed is None:
            failures.append(f"{label}: not on the new registry at all")
            print(f"{RED}MISS{RESET}  {label}")
            continue

        verdict = landed["verdict"]
        if isinstance(verdict, (list, tuple)) and verdict:
            verdict = verdict[0]
        problems = []
        if bytes(landed["content_hash"]).hex() != row["content_hash"]:
            problems.append("content_hash")
        if str(verdict) != row["verdict"]:
            problems.append(f"verdict {verdict} != {row['verdict']}")
        if int(landed["trust_score"]) != row["trust_score"]:
            problems.append("trust_score")
        if bytes(landed["evidence_hash"]).hex() != row["evidence_hash"]:
            problems.append("evidence_hash")
        if address_of(landed["owner"]) != row["owner"]:
            problems.append("owner")

        badge_now = bool(onchain.simulate(
            new, new_tokens, "is_verified_token",
            [scval.to_string(skill_id), scval.to_string(version)],
        ))
        if badge_now != row["badge"]:
            problems.append(f"badge {badge_now} != {row['badge']}")
        # The badge must also still be the thing the registry says it is.
        safe_now = bool(onchain.simulate(
            new, new_registry, "is_verified",
            [scval.to_string(skill_id), scval.to_string(version)],
        ))
        if badge_now != safe_now:
            problems.append(f"badge {badge_now} but registry is_verified {safe_now}")

        if problems:
            failures.append(f"{label}: {', '.join(problems)}")
            print(f"{RED}BAD {RESET}  {label}: {', '.join(problems)}")
        else:
            print(f"{GREEN}ok{RESET}    {skill_id:52} {version:10} "
                  f"{row['verdict']:10} {row['trust_score']:>3} "
                  f"{'badge' if badge_now else ''}")

    count = onchain.simulate(new, new_registry, "get_skill_count")
    supply = onchain.simulate(new, new_tokens, "total_supply")
    print()
    print(f"new registry skill_count = {count}   new tokens total_supply = {supply}")
    print(f"{len(rows)} version(s) checked, {len(failures)} problem(s).")
    for failure in failures:
        print(f"  x {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
