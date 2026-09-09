"""Measure `GET /skills` against live testnet, serial vs concurrent (STE-33).

Run from `api/` with the repo `.env` loaded:

    set -a && . ../.env && set +a
    INDEXER_ENABLED=0 uv run python scripts/measure_skills_fanout.py

Serial mode is the pre-STE-33 behaviour (`chain_concurrency = 1`), so both columns
are measured on the same machine against the same RPC node in the same minute —
comparing a local build against the deployed one would mostly measure the network.
"""

from __future__ import annotations

import statistics
import time

from fastapi.testclient import TestClient

from sterish_api.config import settings
from sterish_api.main import app

LIMITS = (3, 20, 50)
#: Public RPC latency is noisy enough that a single sample can be off by 2x. Report
#: the median of a few, so a number written into the ticket is one that holds up.
REPEATS = 3


def timed(client: TestClient, limit: int) -> tuple[float, int]:
    started = time.monotonic()
    response = client.get(f"/skills?limit={limit}")
    elapsed = time.monotonic() - started
    response.raise_for_status()
    return elapsed, len(response.json()["skills"])


def main() -> None:
    print(f"registry {settings.registry_contract_id}")
    print(f"rpc      {settings.rpc_url}")
    print(f"median of {REPEATS} runs per cell\n")

    configured = settings.chain_concurrency
    results: dict[int, dict[int, float]] = {}
    rows_seen = 0

    with TestClient(app) as client:
        # Warm the connection so the first sample does not pay for TLS setup.
        client.get("/skills?limit=1")

        for concurrency in (1, configured):
            object.__setattr__(settings, "chain_concurrency", concurrency)
            results[concurrency] = {}
            label = "serial" if concurrency == 1 else f"concurrency={concurrency}"
            for limit in LIMITS:
                samples = []
                for _ in range(REPEATS):
                    elapsed, rows_seen = timed(client, limit)
                    samples.append(elapsed)
                median = statistics.median(samples)
                results[concurrency][limit] = median
                spread = "/".join(f"{s:.1f}" for s in samples)
                print(f"{label:>16}  limit={limit:<4} {median:6.2f}s   [{spread}]")

    print(f"\n| `limit` | rows | serial | concurrency={configured} | speedup |")
    print("| -- | -- | -- | -- | -- |")
    for limit in LIMITS:
        before, after = results[1][limit], results[configured][limit]
        rows = min(limit, rows_seen) if limit != LIMITS[-1] else rows_seen
        print(f"| {limit} | {rows} | {before:.1f}s | {after:.1f}s | {before / after:.1f}x |")


if __name__ == "__main__":
    main()
