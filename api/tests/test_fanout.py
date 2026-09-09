"""The bounded fan-out helper itself (STE-33).

These assert the three properties the routes depend on: results come back in input
order, no more than `concurrency` calls are ever in flight, and the calls really do
overlap rather than merely being wrapped in a pool.
"""

import threading
import time

import pytest

from sterish_api import fanout


def test_results_keep_input_order():
    # Reversed sleeps: a pool that returned completion-order would come back backwards.
    def slow_for_small(n: int) -> int:
        time.sleep((10 - n) * 0.01)
        return n * 2

    assert fanout.map_bounded(slow_for_small, range(10), concurrency=10) == [
        n * 2 for n in range(10)
    ]


def test_empty_input_never_starts_a_pool():
    assert fanout.map_bounded(lambda x: x, [], concurrency=8) == []


@pytest.mark.parametrize("concurrency", [0, 1])
def test_non_positive_concurrency_runs_serially(concurrency):
    """`concurrency <= 1` must stay on the calling thread, not spawn a 1-worker pool."""
    caller = threading.current_thread()
    seen = []

    def record(n: int) -> int:
        seen.append(threading.current_thread())
        return n

    assert fanout.map_bounded(record, [1, 2, 3], concurrency=concurrency) == [1, 2, 3]
    assert all(t is caller for t in seen)


def test_concurrency_is_actually_bounded():
    """The ceiling is the point: an unbounded pool would open every socket at once."""
    limit = 4
    in_flight = 0
    peak = 0
    lock = threading.Lock()

    def tracked(n: int) -> int:
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.02)
        with lock:
            in_flight -= 1
        return n

    fanout.map_bounded(tracked, range(40), concurrency=limit)
    assert peak <= limit
    assert peak > 1, "nothing overlapped; the work was not concurrent at all"


def test_calls_overlap_rather_than_queue():
    """20 x 50ms serially is 1.0s. Overlapped 10 at a time it is ~0.1s.

    This is the measurement STE-33 exists for, shrunk to test size.
    """
    started = time.monotonic()
    fanout.map_bounded(lambda _: time.sleep(0.05), range(20), concurrency=10)
    elapsed = time.monotonic() - started
    assert elapsed < 0.5, f"took {elapsed:.2f}s; the calls did not overlap"


def test_exception_propagates_like_a_serial_loop():
    """Per-row error policy belongs in `fn`; anything it raises must reach the caller."""

    def boom(n: int) -> int:
        if n == 3:
            raise ValueError("row 3 is bad")
        return n

    with pytest.raises(ValueError, match="row 3"):
        fanout.map_bounded(boom, range(8), concurrency=4)


def test_every_item_is_visited_exactly_once():
    lock = threading.Lock()
    seen: list[int] = []

    def record(n: int) -> int:
        with lock:
            seen.append(n)
        return n

    fanout.map_bounded(record, range(50), concurrency=8)
    assert sorted(seen) == list(range(50))
