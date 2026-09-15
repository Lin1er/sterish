"""Check every published report against what the registry actually holds.

The project's central claim is that `sha256(report bytes) == evidence_hash` on chain.
Asserting that from the orchestrator's return value proves nothing — it would be
checking our own arithmetic. So this reads each version back with `get_version` and
compares against the file on disk.

Run from the pipeline directory, with .env loaded:

    set -a && . ../.env && set +a
    uv run python scripts/verify_onchain.py ../reports

Exit status is 0 only when every report matches. Nothing here needs a secret key:
every call is a simulation from a throwaway account.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from sterish_pipeline import onchain
from sterish_pipeline.config import PipelineConfig


def config() -> PipelineConfig:
    return PipelineConfig(
        registry_contract_id=os.environ["REGISTRY_CA"],
        rpc_url=os.getenv("STELLAR_RPC_URL", PipelineConfig().rpc_url),
        network_passphrase=os.getenv(
            "STELLAR_NETWORK_PASSPHRASE", PipelineConfig().network_passphrase
        ),
    )


def published(reports_dir: Path) -> list[tuple[str, str, Path]]:
    """(skill_id, version, path) for every report on disk, sorted."""
    out = []
    for skill_dir in sorted(p for p in reports_dir.iterdir() if p.is_dir()):
        for report in sorted(skill_dir.glob("*.json")):
            out.append((skill_dir.name, report.stem, report))
    return out


def main(argv: list[str]) -> int:
    reports_dir = Path(argv[1] if len(argv) > 1 else "../reports")
    cfg = config()
    tokens_id = os.getenv("TOKENS_CA", "")

    failures: list[str] = []
    rows = published(reports_dir)
    print(f"{'skill_id':52} {'version':10} {'verdict':10} {'score':>5}  hash  badge")

    for skill_id, version, path in rows:
        try:
            record = onchain.get_version(cfg, cfg.registry_contract_id, skill_id, version)
        except onchain.OnChainError as exc:
            failures.append(f"{skill_id}@{version}: not readable from chain: {exc}")
            continue

        verdict = record["verdict"]
        if isinstance(verdict, (list, tuple)) and verdict:
            verdict = verdict[0]
        on_chain = bytes(record["evidence_hash"]).hex()
        on_disk = hashlib.sha256(path.read_bytes()).hexdigest()
        content_hash = bytes(record["content_hash"]).hex()

        matched = on_chain == on_disk
        if not matched:
            failures.append(
                f"{skill_id}@{version}: evidence_hash {on_chain[:16]}… does not hash the "
                f"report at {path} ({on_disk[:16]}…)"
            )
        # STE-32 found the STE-13 manual seed storing the content_hash in the
        # evidence_hash slot. Catch that specific mistake by name, not by luck.
        if on_chain == content_hash:
            failures.append(
                f"{skill_id}@{version}: evidence_hash equals content_hash — the wrong "
                "argument was passed to submit_verdict"
            )

        badge = None
        if tokens_id:
            badge = bool(onchain.simulate(
                cfg, tokens_id, "is_verified_token",
                [onchain.scval.to_string(skill_id), onchain.scval.to_string(version)],
            ))
            if badge != (str(verdict) == "Safe"):
                failures.append(
                    f"{skill_id}@{version}: verdict {verdict} but VERIFIED badge is {badge}"
                )

        print(
            f"{skill_id:52} {version:10} {str(verdict):10} {record['trust_score']:>5}  "
            f"{'ok' if matched else 'BAD':5} {badge}"
        )

    print(f"\n{len(rows)} report(s) checked, {len(failures)} problem(s).")
    for failure in failures:
        print(f"  x {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
