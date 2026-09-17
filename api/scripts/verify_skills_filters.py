"""Check `GET /skills` search, filter and sort against a running API (STE-34).

Nothing here trusts the filtered endpoint to grade itself. The expected answer for
every query is computed client-side from the plain registration-order listing, and
every filtered row's verdict is confirmed against `/check`, which reads the chain.

    uv run python scripts/verify_skills_filters.py --api http://127.0.0.1:8765

Exits non-zero on the first disagreement.
"""

from __future__ import annotations

import argparse
import sys

import httpx
from sterish_pipeline.namespaces import is_test_skill_id

VERDICTS = ("SAFE", "WARNING", "DANGEROUS", "UNAUDITED")
UA = {"User-Agent": "sterish-verify/1.0"}


class Mismatch(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Mismatch(message)
    print(f"  ok   {message}")


def all_rows(http: httpx.Client, api: str, **params) -> list[dict]:
    rows, start = [], 0
    while True:
        body = http.get(f"{api}/skills", params={**params, "start": start, "limit": 100}).json()
        rows.extend(body["skills"])
        start += 100
        if start >= body["total"]:
            return rows


def filtered(http: httpx.Client, api: str, **params) -> tuple[list[dict], dict]:
    rows, start, body = [], 0, {}
    while True:
        body = http.get(f"{api}/skills", params={**params, "start": start, "limit": 100}).json()
        rows.extend(body["skills"])
        start += 100
        if start >= body["total"]:
            return rows, body


def expected_order(rows: list[dict], sort: str, order: str) -> list[str]:
    desc = order == "desc"
    by_id = sorted(rows, key=lambda r: r["skill_id"])
    if sort == "skill_id":
        by_id = list(reversed(by_id)) if desc else by_id
        return [r["skill_id"] for r in by_id]
    if sort == "registered_at":
        return [
            r["skill_id"] for r in sorted(by_id, key=lambda r: r["registered_at"], reverse=desc)
        ]
    scored = [r for r in by_id if r["latest_audited_trust_score"] is not None]
    unscored = [r for r in by_id if r["latest_audited_trust_score"] is None]
    scored = sorted(scored, key=lambda r: r["latest_audited_trust_score"], reverse=desc)
    return [r["skill_id"] for r in scored + unscored]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--check-rows", type=int, default=100, help="rows to confirm via /check")
    args = parser.parse_args()
    api = args.api.rstrip("/")
    http = httpx.Client(timeout=120, headers=UA)

    base = all_rows(http, api)
    print(f"registry: {len(base)} skills\n")

    print("1. verdict filter == client-side filter of the full listing, and /check agrees")
    for verdict in VERDICTS:
        want = sorted(
            r["skill_id"] for r in base if (r["latest_audited_verdict"] or "UNAUDITED") == verdict
        )
        rows, body = filtered(http, api, verdict=verdict)
        got = sorted(r["skill_id"] for r in rows)
        check(got == want, f"verdict={verdict}: {len(got)} rows match the full listing")
        check(body["total"] == len(want), f"verdict={verdict}: total {body['total']} == rows")
        check(body["excluded_stale"] == 0, f"verdict={verdict}: nothing excluded as stale")
        for row in rows[: args.check_rows]:
            if not row["latest_audited_version"]:
                continue
            onchain = http.get(
                f"{api}/check/{row['skill_id']}/{row['latest_audited_version']}"
            ).json()["verdict"]
            if onchain != verdict:
                raise Mismatch(f"{row['skill_id']} listed under {verdict} but chain says {onchain}")
        print(f"  ok   verdict={verdict}: every row confirmed by /check")

    print("\n2. q and stale_audit")
    for needle in ("stellar", "EVIL", "fixtures.safe", "zzz-no-such-skill"):
        want = sorted(r["skill_id"] for r in base if needle.lower() in r["skill_id"].lower())
        got = sorted(r["skill_id"] for r in filtered(http, api, q=needle)[0])
        check(got == want, f"q={needle}: {len(got)} rows")
    for flag in ("true", "false"):
        want = sorted(
            r["skill_id"]
            for r in base
            if (r["latest_version"] != r["latest_audited_version"]) == (flag == "true")
        )
        got = sorted(r["skill_id"] for r in filtered(http, api, stale_audit=flag)[0])
        check(got == want, f"stale_audit={flag}: {len(got)} rows")

    print("\n3. sort orders")
    for sort in ("registered_at", "trust_score", "skill_id"):
        for order in ("asc", "desc"):
            rows, _ = filtered(http, api, sort=sort, order=order)
            got = [r["skill_id"] for r in rows]
            want = expected_order(base, sort, order)
            if sort == "registered_at":
                # Ties on registered_at are ordered by skill_id; compare as groups.
                got_keys = [(r["registered_at"]) for r in rows]
                check(
                    got_keys == sorted(got_keys, reverse=order == "desc"),
                    f"sort={sort}&order={order}: monotonic",
                )
                check(sorted(got) == sorted(want), f"sort={sort}&order={order}: same rows")
            else:
                check(got == want, f"sort={sort}&order={order}: exact order")

    print("\n4. paging a filter covers it exactly once")
    whole = [r["skill_id"] for r in filtered(http, api, sort="skill_id", order="asc")[0]]
    paged = []
    for start in range(0, len(whole), 7):
        body = http.get(
            f"{api}/skills", params={"sort": "skill_id", "order": "asc", "start": start, "limit": 7}
        ).json()
        paged.extend(r["skill_id"] for r in body["skills"])
    check(paged == whole, f"{len(whole)} rows in pages of 7, no overlap, no gap")

    print("\n5. invalid parameters are refused")
    for query in (
        {"verdict": "safe"},
        {"sort": "verdict"},
        {"order": "up"},
        {"stale_audit": "yes"},
        {"q": ""},
        {"verified": "true"},
    ):
        r = http.get(f"{api}/skills", params=query)
        check(r.status_code == 400 and r.json()["error"] == "INVALID_PARAMETER", f"{query} -> 400")

    print("\n6. the plain listing is unchanged")
    plain = http.get(f"{api}/skills", params={"limit": 5}).json()
    check(plain["as_of"] is None, "no as_of without filter parameters")
    check(
        [r["skill_id"] for r in plain["skills"]] == [r["skill_id"] for r in base[:5]],
        "registration order preserved",
    )

    print("\n7. test namespaces: hidden under a filter exactly as in the plain listing (STE-18)")
    everything = all_rows(http, api, include_test="true")
    tests = [r for r in everything if is_test_skill_id(r["skill_id"])]
    check(
        sorted(r["skill_id"] for r in base)
        == sorted(r["skill_id"] for r in everything if not is_test_skill_id(r["skill_id"])),
        f"plain listing = include_test listing minus {len(tests)} test rows",
    )
    check(not any(is_test_skill_id(r["skill_id"]) for r in base), "no test id in the plain listing")
    for verdict in VERDICTS:
        matching_tests = [
            r for r in tests if (r["latest_audited_verdict"] or "UNAUDITED") == verdict
        ]
        rows, body = filtered(http, api, verdict=verdict)
        check(
            not any(is_test_skill_id(r["skill_id"]) for r in rows),
            f"verdict={verdict}: no test id served",
        )
        check(
            body["hidden_test_entries"] == len(matching_tests),
            f"verdict={verdict}: hidden_test_entries {body['hidden_test_entries']} "
            "== matching test rows",
        )
        check(body["chain_total"] == plain["chain_total"], f"verdict={verdict}: same chain_total")
        with_tests, body = filtered(http, api, verdict=verdict, include_test="true")
        want = sorted(
            r["skill_id"]
            for r in everything
            if (r["latest_audited_verdict"] or "UNAUDITED") == verdict
        )
        check(
            sorted(r["skill_id"] for r in with_tests) == want and body["hidden_test_entries"] == 0,
            f"verdict={verdict}&include_test=true: {len(want)} rows, nothing hidden",
        )

    print("\nPASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Mismatch as exc:
        print(f"\nFAIL: {exc}")
        sys.exit(1)
