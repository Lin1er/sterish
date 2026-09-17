"""`GET /skills` search, filter and sort (STE-34), with the chain stubbed.

The registry below is deliberately awkward: a never-audited skill, a stale audit, a
row whose record cannot be read, duplicate trust scores and duplicate registration
times, so that every ordering rule and every "unknown is not UNAUDITED" rule has
something to bite on.
"""

import threading
import time

import pytest

from sterish_api import chain, indexer, registry_snapshot
from tests.conftest import SAFE_RECORD

OWNER = "G" + "A" * 55


def _entry(skill_id, registered_at, latest="1.0.0", audited="1.0.0", versions=1):
    return {
        "skill_id": skill_id,
        "owner": OWNER,
        "versions": [f"1.0.{n}" for n in range(versions)],
        "latest_version": latest,
        "latest_audited_version": audited,
        "registered_at": registered_at,
    }


# skill_id -> (entry, record-or-exception)
REGISTRY = {
    "com.acme.pdf-suite": (_entry("com.acme.pdf-suite", 100), ("SAFE", 88)),
    "com.acme.weather": (_entry("com.acme.weather", 200), ("SAFE", 95)),
    "com.evil.wallet-drainer": (_entry("com.evil.wallet-drainer", 300), ("DANGEROUS", 10)),
    "com.evil.pdf-stealer": (_entry("com.evil.pdf-stealer", 300), ("DANGEROUS", 10)),
    "org.example.half-sure": (_entry("org.example.half-sure", 400), ("WARNING", 60)),
    "org.example.never-audited": (
        _entry("org.example.never-audited", 500, audited=None),
        None,
    ),
    "org.example.stale": (
        _entry("org.example.stale", 600, latest="2.0.0", audited="1.0.0", versions=2),
        ("SAFE", 70),
    ),
    "org.example.unreadable": (_entry("org.example.unreadable", 700), "unreadable"),
}
ORDER = list(REGISTRY)  # registration order


class Chain:
    """A fake registry that counts its reads."""

    def __init__(self, monkeypatch, registry=None):
        self.registry = dict(registry or REGISTRY)
        self.order = list(self.registry)
        self.count_calls = 0
        self.page_calls: list[tuple[int, int]] = []
        self.version_calls = 0
        self.overrides: dict[str, tuple[str, int]] = {}
        self.lock = threading.Lock()
        monkeypatch.setattr(chain, "get_skill_count", self.get_skill_count)
        monkeypatch.setattr(chain, "query_all_skills", self.query_all_skills)
        monkeypatch.setattr(chain, "get_version", self.get_version)

    def get_skill_count(self):
        with self.lock:
            self.count_calls += 1
        return len(self.order)

    def query_all_skills(self, start, limit):
        with self.lock:
            self.page_calls.append((start, limit))
        return [self.registry[s][0] for s in self.order[start : start + limit]]

    def get_version(self, skill_id, version):
        with self.lock:
            self.version_calls += 1
        spec = self.overrides.get(skill_id) or self.registry[skill_id][1]
        if spec == "unreadable":
            raise chain.ContractError(4)
        verdict, score = spec
        return dict(
            SAFE_RECORD,
            skill_id=skill_id,
            version=version,
            verdict=verdict,
            trust_score=score,
            is_verified=verdict == "SAFE",
        )


@pytest.fixture
def registry(monkeypatch):
    return Chain(monkeypatch)


def ids(response):
    return [row["skill_id"] for row in response.json()["skills"]]


# --- the plain listing is unchanged ----------------------------------------------------------


def test_no_parameters_keeps_registration_order_and_contract_total(client, registry):
    r = client.get("/skills?limit=100")
    body = r.json()
    assert ids(r) == ORDER
    assert body["total"] == len(ORDER)
    assert body["as_of"] is None and body["excluded_stale"] == 0


def test_plain_start_and_limit_page_the_scanned_registry_as_on_main(client, registry):
    # Since STE-18 the plain listing scans the registry and pages the visible rows, so
    # that hiding test namespaces cannot leave holes in a page. STE-34 leaves that path
    # exactly as it is.
    r = client.get("/skills?start=2&limit=3")
    assert ids(r) == ORDER[2:5]
    assert registry.page_calls == [(0, 100)]


# --- filters -----------------------------------------------------------------------------------


def test_verdict_filter_returns_only_that_verdict_and_counts_after_filtering(client, registry):
    r = client.get("/skills?verdict=DANGEROUS")
    body = r.json()
    assert sorted(ids(r)) == ["com.evil.pdf-stealer", "com.evil.wallet-drainer"]
    assert body["total"] == 2  # not the registry's 8
    assert all(row["latest_audited_verdict"] == "DANGEROUS" for row in body["skills"])
    assert body["as_of"] is not None


def test_a_filter_with_no_matches_is_an_empty_page_not_an_error(client, registry):
    registry.registry.pop("org.example.half-sure")
    registry.order.remove("org.example.half-sure")
    r = client.get("/skills?verdict=WARNING")
    assert r.status_code == 200
    assert r.json() == {
        "skills": [],
        "total": 0,
        "start": 0,
        "limit": 20,
        "chain_total": len(registry.order),
        "hidden_test_entries": 0,
        "include_test": False,
        "as_of": r.json()["as_of"],
        "excluded_stale": 0,
    }


def test_unaudited_means_never_audited_not_unreadable(client, registry):
    """A row whose record failed to read is unknown. Calling it UNAUDITED would be a
    claim about the registry that the registry never made."""
    r = client.get("/skills?verdict=UNAUDITED")
    assert ids(r) == ["org.example.never-audited"]


def test_an_unreadable_row_matches_no_verdict_at_all(client, registry):
    for verdict in ("SAFE", "WARNING", "DANGEROUS", "UNAUDITED"):
        assert "org.example.unreadable" not in ids(client.get(f"/skills?verdict={verdict}"))


def test_an_unreadable_row_still_appears_without_a_verdict_filter(client, registry):
    r = client.get("/skills?q=unreadable")
    assert ids(r) == ["org.example.unreadable"]
    assert r.json()["skills"][0]["latest_audited_verdict"] is None


def test_q_is_a_case_insensitive_substring_of_skill_id(client, registry):
    assert sorted(ids(client.get("/skills?q=PDF"))) == [
        "com.acme.pdf-suite",
        "com.evil.pdf-stealer",
    ]
    assert ids(client.get("/skills?q=nothing-like-this")) == []


def test_q_is_trimmed(client, registry):
    assert ids(client.get("/skills?q=%20weather%20")) == ["com.acme.weather"]


def test_stale_audit_true_includes_never_audited(client, registry):
    r = client.get("/skills?stale_audit=true")
    assert sorted(ids(r)) == ["org.example.never-audited", "org.example.stale"]


def test_stale_audit_false_is_the_complement(client, registry):
    stale = set(ids(client.get("/skills?stale_audit=true&limit=100")))
    fresh = set(ids(client.get("/skills?stale_audit=false&limit=100")))
    assert stale.isdisjoint(fresh) and stale | fresh == set(ORDER)


def test_filters_combine(client, registry):
    r = client.get("/skills?verdict=SAFE&stale_audit=true")
    assert ids(r) == ["org.example.stale"]
    r = client.get("/skills?verdict=SAFE&q=acme&sort=trust_score&order=desc")
    assert ids(r) == ["com.acme.weather", "com.acme.pdf-suite"]


# --- sorting ------------------------------------------------------------------------------------


def test_filtered_default_order_is_newest_registration_first(client, registry):
    r = client.get("/skills?q=com.")
    # 300 twice: ties break on skill_id ascending.
    assert ids(r) == [
        "com.evil.pdf-stealer",
        "com.evil.wallet-drainer",
        "com.acme.weather",
        "com.acme.pdf-suite",
    ]


def test_registered_at_ascending(client, registry):
    r = client.get("/skills?sort=registered_at&order=asc&limit=100")
    assert ids(r)[:2] == ["com.acme.pdf-suite", "com.acme.weather"]
    assert ids(r)[-1] == "org.example.unreadable"


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_rows_without_a_trust_score_sort_last_in_both_directions(client, registry, order):
    r = client.get(f"/skills?sort=trust_score&order={order}&limit=100")
    assert ids(r)[-2:] == ["org.example.never-audited", "org.example.unreadable"]
    scores = [row["latest_audited_trust_score"] for row in r.json()["skills"][:-2]]
    assert scores == sorted(scores, reverse=order == "desc")


def test_equal_trust_scores_break_on_skill_id(client, registry):
    r = client.get("/skills?sort=trust_score&order=asc&limit=2")
    assert ids(r) == ["com.evil.pdf-stealer", "com.evil.wallet-drainer"]


def test_skill_id_sort_both_ways(client, registry):
    asc = ids(client.get("/skills?sort=skill_id&order=asc&limit=100"))
    assert asc == sorted(ORDER)
    assert ids(client.get("/skills?sort=skill_id&order=desc&limit=100")) == list(reversed(asc))


def test_order_alone_applies_to_the_default_sort(client, registry):
    assert ids(client.get("/skills?order=asc&limit=100")) == ids(
        client.get("/skills?sort=registered_at&order=asc&limit=100")
    )


# --- paging over filtered results ---------------------------------------------------------------


def test_pages_over_a_filter_do_not_overlap_and_cover_everything(client, registry):
    whole = ids(client.get("/skills?sort=skill_id&order=asc&limit=100"))
    pages = []
    for start in range(0, len(whole), 3):
        r = client.get(f"/skills?sort=skill_id&order=asc&start={start}&limit=3")
        assert r.json()["total"] == len(whole)
        pages.extend(ids(r))
    assert pages == whole


def test_start_past_the_end_is_an_empty_page_with_the_real_total(client, registry):
    body = client.get("/skills?verdict=SAFE&start=50").json()
    assert body["skills"] == [] and body["total"] == 3


def test_only_the_returned_page_is_read_live(client, registry):
    client.get("/skills?sort=skill_id&limit=100")  # build the snapshot
    before = registry.version_calls
    client.get("/skills?sort=skill_id&limit=2")
    assert registry.version_calls - before == 2


# --- invalid parameters ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "verdict=safe",
        "verdict=VERIFIED",
        "verdict=",
        "sort=verdict",
        "sort=owner",
        "order=up",
        "stale_audit=yes",
        "stale_audit=1",
        "q=",
        "q=%20%20",
        "q=" + "x" * 201,
        "verified=true",
        "owner=" + OWNER,
    ],
)
def test_invalid_parameters_are_400_never_ignored(client, registry, query):
    r = client.get(f"/skills?{query}")
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "INVALID_PARAMETER"


def test_rejected_parameters_say_what_to_use_instead(client, registry):
    assert "verdict=SAFE" in client.get("/skills?verified=true").json()["detail"]


# --- snapshot versus chain ------------------------------------------------------------------------


def test_a_row_whose_live_verdict_changed_is_left_out_and_the_view_refreshed(client, registry):
    """The edge case the ticket names: chosen as SAFE, reads DANGEROUS now."""
    assert "com.acme.weather" in ids(client.get("/skills?verdict=SAFE"))

    registry.overrides["com.acme.weather"] = ("DANGEROUS", 5)  # re-audited on chain
    r = client.get("/skills?verdict=SAFE")
    body = r.json()
    assert "com.acme.weather" not in ids(r)
    assert body["excluded_stale"] == 1
    assert all(row["latest_audited_verdict"] == "SAFE" for row in body["skills"])

    # The next request rebuilds and agrees with the chain everywhere.
    assert "com.acme.weather" not in ids(client.get("/skills?verdict=SAFE"))
    assert "com.acme.weather" in ids(client.get("/skills?verdict=DANGEROUS"))
    assert client.get("/skills?verdict=SAFE").json()["excluded_stale"] == 0


def test_without_a_verdict_filter_the_live_verdict_is_shown(client, registry):
    client.get("/skills?q=weather")
    registry.overrides["com.acme.weather"] = ("DANGEROUS", 5)
    row = client.get("/skills?q=weather").json()["skills"][0]
    assert row["latest_audited_verdict"] == "DANGEROUS"


def test_a_row_that_becomes_unreadable_is_excluded_from_a_verdict_filter(client, registry):
    client.get("/skills?verdict=SAFE")
    registry.overrides["com.acme.weather"] = "unreadable"
    r = client.get("/skills?verdict=SAFE")
    assert "com.acme.weather" not in ids(r)
    assert r.json()["excluded_stale"] == 1


def test_the_snapshot_is_reused_within_its_ttl(client, registry):
    client.get("/skills?verdict=SAFE")
    client.get("/skills?verdict=DANGEROUS")
    client.get("/skills?q=acme")
    assert registry.count_calls == 1


def test_the_snapshot_expires(client, registry, monkeypatch):
    client.get("/skills?verdict=SAFE")
    real = time.time
    monkeypatch.setattr(registry_snapshot.time, "time", lambda: real() + 3600)
    client.get("/skills?verdict=SAFE")
    assert registry.count_calls == 2


def test_a_new_indexed_event_drops_the_snapshot(client, registry):
    client.get("/skills?verdict=SAFE")
    registry.registry["com.new.skill"] = (_entry("com.new.skill", 900), ("SAFE", 99))
    registry.order.append("com.new.skill")
    assert "com.new.skill" not in ids(client.get("/skills?verdict=SAFE&limit=100"))

    stored = indexer._store(
        [
            {
                "event": "skill_registered",
                "skill_id": "com.new.skill",
                "version": "",
                "content_hash": None,
                "verdict": None,
                "trust_score": None,
                "owner": OWNER,
                "auditor": None,
                "ledger": 1,
                "tx_hash": "f" * 64,
                "occurred_at": 1,
            }
        ]
    )
    assert stored == 1
    # _store only writes; poll_once is what drops the view. Exercise that path.
    registry_snapshot.invalidate()
    assert "com.new.skill" in ids(client.get("/skills?verdict=SAFE&limit=100"))


def test_poll_once_drops_the_snapshot_when_it_stores_events(client, registry, monkeypatch):
    client.get("/skills?verdict=SAFE")
    dropped = []
    monkeypatch.setattr(registry_snapshot, "invalidate", lambda: dropped.append(1))

    class Health:
        oldest_ledger = 10

    class Server:
        def __init__(self, url):
            pass

        def get_health(self):
            return Health()

        def get_latest_ledger(self):
            return type("L", (), {"sequence": 10})()

    event_row = {
        "event": "verdict_flipped",
        "skill_id": "com.acme.weather",
        "version": "1.0.0",
        "content_hash": None,
        "verdict": "DANGEROUS",
        "trust_score": 5,
        "owner": None,
        "auditor": None,
        "ledger": 10,
        "tx_hash": "e" * 64,
        "occurred_at": 1,
    }
    from sterish_api.config import settings

    object.__setattr__(settings, "registry_contract_id", settings.registry_contract_id or "C")
    monkeypatch.setattr(indexer, "SorobanServer", Server)
    monkeypatch.setattr(
        indexer, "_get_events", lambda server, start: type("R", (), {"events": [1]})()
    )
    monkeypatch.setattr(indexer, "_decode_event", lambda ev: dict(event_row))

    indexer.poll_once()
    assert dropped == [1]

    dropped.clear()
    indexer.poll_once()  # same event again: INSERT OR IGNORE stores nothing
    assert dropped == []


def test_the_snapshot_reads_the_registry_in_pages_of_100(client, monkeypatch):
    big = {
        f"com.bulk.skill-{n:03d}": (_entry(f"com.bulk.skill-{n:03d}", n), ("SAFE", n % 100))
        for n in range(250)
    }
    fake = Chain(monkeypatch, registry=big)
    r = client.get("/skills?sort=skill_id&order=asc&start=240&limit=100")
    assert r.json()["total"] == 250
    assert ids(r)[0] == "com.bulk.skill-240"
    assert fake.page_calls == [(0, 100), (100, 100), (200, 100)]


def test_concurrent_requests_build_the_snapshot_once(client, registry, monkeypatch):
    real = registry.get_skill_count

    def slow_count():
        time.sleep(0.2)
        return real()

    monkeypatch.setattr(chain, "get_skill_count", slow_count)
    results = []

    def fetch():
        results.append(client.get("/skills?verdict=SAFE").status_code)

    threads = [threading.Thread(target=fetch) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200] * 6
    assert registry.count_calls == 1


def test_a_view_invalidated_during_its_build_is_not_kept(registry, monkeypatch):
    real = registry.get_skill_count

    def count_then_invalidate():
        n = real()
        registry_snapshot.invalidate()  # an event lands mid-build
        return n

    monkeypatch.setattr(chain, "get_skill_count", count_then_invalidate)
    first = registry_snapshot.get()
    assert len(first.rows) == len(ORDER)  # the waiting caller still gets an answer
    monkeypatch.setattr(chain, "get_skill_count", real)
    registry_snapshot.get()
    assert registry.count_calls == 2  # ...but it was not cached


def test_an_unreadable_registry_is_502_not_an_empty_page(client, monkeypatch):
    def down():
        raise chain.ChainError("rpc down")

    monkeypatch.setattr(chain, "get_skill_count", down)
    r = client.get("/skills?verdict=SAFE")
    assert r.status_code == 502
    assert r.json()["error"] == "RPC_UNAVAILABLE"


# --- test namespaces stay hidden under a filter too (STE-18) ----------------------------------

TEST_ROWS = {
    "com.sterish.e2e-safe-probe": (_entry("com.sterish.e2e-safe-probe", 800), ("SAFE", 99)),
    "com.sterish.weather-lookup": (_entry("com.sterish.weather-lookup", 900), ("DANGEROUS", 5)),
}


@pytest.fixture
def mixed(monkeypatch):
    return Chain(monkeypatch, registry={**REGISTRY, **TEST_ROWS})


def test_a_filter_hides_test_namespaces_and_says_how_many_it_hid(client, mixed):
    body = client.get("/skills?verdict=SAFE&sort=trust_score&order=desc").json()
    returned = [row["skill_id"] for row in body["skills"]]
    assert "com.sterish.e2e-safe-probe" not in returned
    assert returned == ["com.acme.weather", "com.acme.pdf-suite", "org.example.stale"]
    assert body["total"] == 3
    assert body["hidden_test_entries"] == 1  # the SAFE test row; the DANGEROUS one did not match
    assert body["chain_total"] == len(REGISTRY) + len(TEST_ROWS)
    assert body["include_test"] is False


def test_include_test_brings_test_namespaces_back_into_a_filtered_listing(client, mixed):
    body = client.get("/skills?verdict=SAFE&sort=trust_score&order=desc&include_test=true").json()
    assert [row["skill_id"] for row in body["skills"]][0] == "com.sterish.e2e-safe-probe"
    assert body["total"] == 4
    assert body["hidden_test_entries"] == 0
    assert body["include_test"] is True


def test_a_legacy_test_id_is_hidden_by_a_search_that_names_it(client, mixed):
    body = client.get("/skills?q=weather").json()
    assert [row["skill_id"] for row in body["skills"]] == ["com.acme.weather"]
    assert body["hidden_test_entries"] == 1


def test_the_plain_listing_still_hides_every_test_row(client, mixed):
    body = client.get("/skills?limit=100").json()
    assert [row["skill_id"] for row in body["skills"]] == ORDER
    assert body["hidden_test_entries"] == len(TEST_ROWS)
    assert body["as_of"] is None


def test_filtered_and_plain_listings_agree_on_what_is_visible(client, mixed):
    plain = client.get("/skills?limit=100").json()
    sorted_ = client.get("/skills?sort=registered_at&order=asc&limit=100").json()
    # Same rows; the order differs only where registered_at ties (sorted breaks on skill_id).
    assert sorted(r["skill_id"] for r in plain["skills"]) == sorted(
        r["skill_id"] for r in sorted_["skills"]
    )
    assert plain["total"] == sorted_["total"]
    assert plain["chain_total"] == sorted_["chain_total"]
    assert plain["hidden_test_entries"] == sorted_["hidden_test_entries"]


def test_the_snapshot_shares_the_plain_listings_scan_cap(client, monkeypatch):
    from sterish_api import skills

    monkeypatch.setattr(skills, "MAX_SCAN", 5)
    fake = Chain(monkeypatch)
    body = client.get("/skills?sort=skill_id&limit=100").json()
    assert body["total"] == 5
    assert body["chain_total"] == len(ORDER)
    assert fake.page_calls == [(0, 5)]
