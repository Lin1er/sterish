"""Which registry entries the API shows by default, and how it admits what it hid.

The problem
-----------
The testnet registry holds 66 skills. 47 of them are test scaffolding — ids the
integration and end-to-end suites registered on their way past. They cannot be
removed: `contracts/registry` exposes no delete, and no Sterish contract is
upgradeable (there is no `update_current_contract_wasm` anywhere in `contracts/`),
so adding one would mean a new contract address and a full registry migration.

So the filter lives here, in the API. The rule itself is
`sterish_pipeline.namespaces`, shared with the tests that create the ids, because a
filter and a test that disagree about the prefix produce exactly the junk the filter
exists to remove.

The rule this must satisfy
--------------------------
**A reader must never be able to conclude that what the API shows is the whole
chain.** Hiding silently was considered and rejected. So every list response
carries `chain_total` — `get_skill_count()` exactly as the contract returns it —
next to the filtered `total`, plus `hidden_test_entries` and the `include_test`
flag that reveals them. A client that renders only `total` still cannot claim
completeness, because the two numbers are in the same object and differ.

Why the whole registry is scanned
---------------------------------
`query_all_skills(start, limit)` pages over the raw on-chain index, so filtering a
single page would make `start`/`limit` mean "positions in the unfiltered list",
and a page of 20 could come back with 3 rows. Pagination has to run over the
filtered sequence to mean anything, which means knowing the whole sequence. At 66
entries that is one RPC round trip; `MAX_SCAN` caps it so the cost cannot grow
without someone noticing.
"""

from __future__ import annotations

from sterish_pipeline.namespaces import is_test_skill_id

from . import chain

#: Entries per `query_all_skills` call. One round trip covers the current registry.
SCAN_PAGE = 100

#: Hard ceiling on entries scanned for one request. If the registry ever outgrows
#: this, `/skills` starts truncating and the fix is a server-side index, not a
#: bigger number: 5 RPC round trips per list request is already the limit of what
#: a public node should be asked for.
MAX_SCAN = 500


def scan_registry() -> tuple[list[dict], int]:
    """Every skill header the registry holds, plus the contract's own count.

    Returns `(entries, chain_total)`. `len(entries)` can be less than `chain_total`
    when the registry exceeds `MAX_SCAN`, or when the on-chain index has a gap — the
    contract skips an index slot whose entry cannot be read rather than failing the
    whole call, so the two numbers are reported separately instead of one being
    derived from the other.
    """
    chain_total = chain.get_skill_count()
    entries: list[dict] = []
    start = 0
    while start < chain_total and len(entries) < MAX_SCAN:
        page = chain.query_all_skills(start, min(SCAN_PAGE, MAX_SCAN - len(entries)))
        if not page:
            break
        entries.extend(page)
        start += len(page)
    return entries, chain_total


def partition(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split into (published, test scaffolding), preserving on-chain order."""
    published: list[dict] = []
    scaffolding: list[dict] = []
    for entry in entries:
        target = scaffolding if is_test_skill_id(entry["skill_id"]) else published
        target.append(entry)
    return published, scaffolding


def visible_page(start: int, limit: int, include_test: bool) -> tuple[list[dict], int, int, int]:
    """One page of the list, and the three numbers that make it honest.

    Returns `(page, total, chain_total, hidden)`:

    * `page` — the rows to serve, sliced out of the filtered sequence;
    * `total` — how many rows exist under the current filter;
    * `chain_total` — `get_skill_count()`, untouched, always the real number;
    * `hidden` — how many entries the filter removed (0 when `include_test`).
    """
    entries, chain_total = scan_registry()
    published, scaffolding = partition(entries)

    universe = entries if include_test else published
    hidden = 0 if include_test else len(scaffolding)
    return universe[start : start + limit], len(universe), chain_total, hidden
