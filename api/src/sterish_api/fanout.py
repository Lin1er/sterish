"""Bounded concurrent fan-out for the per-row chain reads (STE-33).

`GET /skills` and `GET /skills/{skill_id}` both answer one request with one
`simulateTransaction` **per row**. Run serially that is linear in page size, not in
registry size: measured against the live API on 2026-09-09, `limit=3` took 2.5s,
`limit=20` took 9.9s and `limit=50` took 22.0s — about 0.44s per row, which is one
RPC round trip.

The rows do not depend on each other, so the round trips can overlap. What they must
not do is overlap without a ceiling: a page of 100 would otherwise open 100 sockets
to a public RPC node at once, and being rate-limited is slower than being serial.

Threads rather than asyncio: `chain._invoke_on` is blocking `stellar_sdk` code with no
async variant, and each call builds its own `SorobanServer`, so there is no client
state shared across threads. The route handlers are already sync `def`, which FastAPI
runs in a threadpool, so this nests one bounded pool inside that — it does not touch
the event loop.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

#: Matched to the default page size of `GET /skills`, so the common request resolves in
#: a single wave of round trips. Measured against soroban-testnet on 2026-09-09 with 47
#: skills registered: 8 -> 3.0s, 12 -> 3.1s, 16 -> 2.1s, 20 -> 1.7s, 32 -> 1.6s for
#: `limit=20`. Past 20 the curve flattens, so the extra sockets buy ~0.1s and are not
#: worth pointing at a public node. Override with STERISH_CHAIN_CONCURRENCY.
DEFAULT_CONCURRENCY = 20


def map_bounded[T, R](
    fn: Callable[[T], R],
    items: Iterable[T],
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[R]:
    """Apply `fn` to every item, at most `concurrency` at a time.

    Results are returned **in input order**, so callers can zip them back against the
    rows they came from. An exception raised by `fn` propagates to the caller, exactly
    as it would from a serial loop — per-row error handling belongs inside `fn`, where
    the caller can decide that one unreadable row should not fail the whole page.

    `concurrency <= 1` runs serially and never starts a pool, which keeps the tests
    that assert call ordering deterministic.
    """
    items = list(items)
    if not items:
        return []

    workers = min(max(concurrency, 1), len(items))
    if workers == 1:
        return [fn(item) for item in items]

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sterish-fanout") as pool:
        # `pool.map` yields in input order and re-raises the first failure on iteration.
        return list(pool.map(fn, items))
