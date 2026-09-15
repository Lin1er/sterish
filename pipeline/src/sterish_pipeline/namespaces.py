"""Which `skill_id`s are test scaffolding rather than published skills.

Why this lives in one module
----------------------------
The registry is append-only and **no Sterish contract is upgradeable**: there is no
`remove_skill`, no `update_current_contract_wasm` anywhere in `contracts/`, and
adding one would mean a new contract address and a full migration. So every skill a
test registers on testnet is on the ledger permanently — 47 of them by the time
STE-18 ran, against 19 real entries.

They cannot be deleted, so they are filtered, in the API layer (`sterish_api.skills`
hides them from `/skills` and `/feed` by default while reporting how many it hid).
A filter is only as good as the tests agreeing to register under a prefix it
catches, which is why the prefixes are defined **here**, in the package both the
API and the pipeline's live integration tests import, rather than written out twice.

**If you add a test that registers a skill on chain, build its id with
`new_test_skill_id()`.** An id that does not start with one of these prefixes will be
served to the dashboard as though it were a real audited skill.

Note on the counterpart: `com.fixtures.*` is deliberately NOT in here. Those are
published demo data — the poisoned fixtures that prove the D2 gate and the STE-18
demo set that lights all four registry states — and hiding them would empty the
dashboard of exactly what it is meant to show.
"""

from __future__ import annotations

import time

#: An id starting with one of these is test scaffolding. Prefixes, not a namespace:
#: `com.sterish.` on its own is not a marker, because a genuine Sterish-published
#: skill would live there too.
TEST_SKILL_ID_PREFIXES: tuple[str, ...] = (
    "com.sterish.it-",      # pipeline integration tests (tests/test_live_orchestration.py)
    "com.sterish.e2e-",     # API end-to-end runs against a live deployment
    "com.sterish.canon-",   # canonical rehearsal seeds (docs/deployments.md)
)

#: Registered before the convention existed (STE-13's manual seed) and therefore not
#: matched by any prefix. Named exactly rather than widened into a prefix rule, so the
#: list stays auditable and cannot quietly grow to cover a real skill.
#:
#: STE-32 found `evidence_hash == content_hash` on both of these — the STE-13 seed
#: passed the wrong argument to `submit_verdict`. They are not re-seeded: the bytes
#: are junk, the filter hides them, and the 16 December 2026 testnet reset clears them.
LEGACY_TEST_SKILL_IDS: frozenset[str] = frozenset(
    {
        "com.sterish.weather-lookup",
        "com.evil.token-drainer",
    }
)


def is_test_skill_id(skill_id: str) -> bool:
    """True when `skill_id` is test scaffolding, not a published skill."""
    return skill_id in LEGACY_TEST_SKILL_IDS or skill_id.startswith(TEST_SKILL_ID_PREFIXES)


def new_test_skill_id(kind: str, slug: str, suffix: str | int | None = None) -> str:
    """Build an id for a skill a test is about to register on chain.

    Named `new_test_...` rather than `test_...`: pytest collects any importable
    callable whose name starts with `test`, so the obvious name turns every test
    module that imports it into a collection error.

    `kind` is one of the prefix markers without the `com.sterish.` stem — "it",
    "e2e" or "canon". `suffix` defaults to the current unix time so that a re-run
    registers fresh bytes and genuinely exercises `register_skill` rather than
    bouncing off `VersionAlreadyExists`.

    The frozen verdict schema allows only lowercase alphanumerics, hyphens and dots
    in a skill_id, so the slug is sanitised here rather than failing validation
    somewhere downstream.
    """
    prefix = f"com.sterish.{kind}-"
    if prefix not in TEST_SKILL_ID_PREFIXES:
        raise ValueError(
            f"{kind!r} is not a test-id marker; expected one of "
            f"{[p.removeprefix('com.sterish.').rstrip('-') for p in TEST_SKILL_ID_PREFIXES]}"
        )
    cleaned = "".join(c if c.isalnum() or c == "-" else "-" for c in slug.lower())
    stamp = int(time.time()) if suffix is None else suffix
    return f"{prefix}{cleaned}-{stamp}"


__all__ = [
    "LEGACY_TEST_SKILL_IDS",
    "TEST_SKILL_ID_PREFIXES",
    "is_test_skill_id",
    "new_test_skill_id",
]
