"""The registry shows published skills by default — and admits what it hid (STE-18).

47 of the 66 skills on the testnet registry are test scaffolding. None of it can be
removed: the registry exposes no delete and no Sterish contract is upgradeable, so
the only option is to filter in this layer.

The rule this file exists to pin: **a reader must never be able to conclude that
what the API shows is the whole chain.** Hiding silently was considered and
rejected, so every count a filtered response leaves out is reported next to the one
it leaves in.
"""

import pytest
from sterish_pipeline.namespaces import is_test_skill_id

from sterish_api import chain, indexer, skills

# The shapes actually read back from chain on 9 Sep 2026: 12 catalog, 7 fixtures,
# and the three junk prefixes plus the two legacy ids.
REAL_IDS = [
    "org.stellar.skills.cross-chain.cctp",
    "org.stellar.skills.dapp.react",
    "com.fixtures.poisoned.pdf-summarizer",
    "com.fixtures.demo.release-notes",
    "com.fixtures.demo.changelog-writer",
]
JUNK_IDS = [
    "com.sterish.it-safe-skill-1788541727",
    "com.sterish.e2e-1788541421",
    "com.sterish.canon-safe-1788685783",
    "com.sterish.weather-lookup",
    "com.evil.token-drainer",
]


def _entry(skill_id: str, n: int = 0) -> dict:
    return {
        "skill_id": skill_id,
        "owner": "G" + "A" * 55,
        "versions": ["1.0.0"],
        "latest_version": "1.0.0",
        "latest_audited_version": None,
        "registered_at": 1_756_800_000 + n,
    }


@pytest.fixture
def registry(monkeypatch):
    """A registry holding the real/junk mix, in the order the chain returns it."""
    entries = [_entry(s, n) for n, s in enumerate(JUNK_IDS + REAL_IDS)]
    monkeypatch.setattr(chain, "query_all_skills",
                        lambda start, limit: entries[start : start + limit])
    monkeypatch.setattr(chain, "get_skill_count", lambda: len(entries))
    return entries


class TestSkillsList:
    def test_test_namespaces_are_hidden_by_default(self, client, registry):
        body = client.get("/skills?limit=100").json()
        served = [row["skill_id"] for row in body["skills"]]
        assert served == REAL_IDS
        assert not any(is_test_skill_id(s) for s in served)

    def test_the_hidden_count_is_reported(self, client, registry):
        """The requirement: a response that hides something says how much."""
        body = client.get("/skills?limit=100").json()
        assert body["hidden_test_entries"] == len(JUNK_IDS)
        assert body["total"] == len(REAL_IDS)

    def test_the_real_chain_count_is_always_present(self, client, registry):
        """`chain_total` is `get_skill_count()` untouched, so no reader can mistake
        the filtered list for the whole chain."""
        body = client.get("/skills?limit=100").json()
        assert body["chain_total"] == len(JUNK_IDS) + len(REAL_IDS)
        assert body["chain_total"] == body["total"] + body["hidden_test_entries"]

    def test_include_test_reveals_them(self, client, registry):
        body = client.get("/skills?limit=100&include_test=true").json()
        served = [row["skill_id"] for row in body["skills"]]
        assert served == JUNK_IDS + REAL_IDS
        assert body["total"] == body["chain_total"]
        assert body["hidden_test_entries"] == 0
        assert body["include_test"] is True

    def test_the_flag_is_echoed_back(self, client, registry):
        assert client.get("/skills").json()["include_test"] is False

    def test_pagination_runs_over_the_filtered_sequence(self, client, registry):
        """`start`/`limit` must index the list the client can see. Filtering one raw
        page instead would make a page of 2 come back with 0 rows."""
        page = client.get("/skills?start=0&limit=2").json()
        assert [r["skill_id"] for r in page["skills"]] == REAL_IDS[:2]
        assert page["total"] == len(REAL_IDS)

        rest = client.get("/skills?start=2&limit=100").json()
        assert [r["skill_id"] for r in rest["skills"]] == REAL_IDS[2:]

    def test_a_registry_of_only_junk_is_not_an_empty_registry(self, client, monkeypatch):
        entries = [_entry(s, n) for n, s in enumerate(JUNK_IDS)]
        monkeypatch.setattr(chain, "query_all_skills",
                            lambda start, limit: entries[start : start + limit])
        monkeypatch.setattr(chain, "get_skill_count", lambda: len(entries))
        body = client.get("/skills").json()
        assert body["skills"] == []
        assert body["total"] == 0
        # ...and the two numbers that stop this reading as "nothing is registered".
        assert body["chain_total"] == len(JUNK_IDS)
        assert body["hidden_test_entries"] == len(JUNK_IDS)


class TestScan:
    def test_the_scan_is_bounded(self, monkeypatch):
        """A registry larger than MAX_SCAN truncates rather than hammering the RPC."""
        huge = [_entry(f"com.acme.s{n}", n) for n in range(skills.MAX_SCAN * 2)]
        monkeypatch.setattr(chain, "query_all_skills",
                            lambda start, limit: huge[start : start + limit])
        monkeypatch.setattr(chain, "get_skill_count", lambda: len(huge))
        entries, chain_total = skills.scan_registry()
        assert len(entries) == skills.MAX_SCAN
        # The contract's number is reported whole even when the scan could not be.
        assert chain_total == len(huge)

    def test_an_empty_page_stops_the_walk(self, monkeypatch):
        """The on-chain index can have a gap; a short page must not loop forever."""
        monkeypatch.setattr(chain, "query_all_skills", lambda start, limit: [])
        monkeypatch.setattr(chain, "get_skill_count", lambda: 40)
        entries, chain_total = skills.scan_registry()
        assert entries == []
        assert chain_total == 40


class TestFeed:
    def _rows(self):
        return [
            {
                "event": "version_registered", "skill_id": skill_id, "version": "1.0.0",
                "content_hash": None, "verdict": None, "trust_score": None,
                "owner": None, "auditor": None, "ledger": 4_482_500 + n,
                "tx_hash": f"{n:064x}", "occurred_at": 1_756_800_000 + n,
            }
            for n, skill_id in enumerate(JUNK_IDS + REAL_IDS)
        ]

    def test_events_from_test_namespaces_are_hidden(self, client):
        indexer._store(self._rows())
        body = client.get("/feed").json()
        assert {e["skill_id"] for e in body["events"]} == set(REAL_IDS)
        assert body["total"] == len(REAL_IDS)
        assert body["hidden_test_events"] == len(JUNK_IDS)

    def test_include_test_reveals_them(self, client):
        indexer._store(self._rows())
        body = client.get("/feed?include_test=true").json()
        assert len(body["events"]) == len(JUNK_IDS) + len(REAL_IDS)
        assert body["hidden_test_events"] == 0
        assert body["include_test"] is True

    def test_sql_prefix_match_agrees_with_the_python_rule(self, client):
        """The feed filters in SQLite and `/skills` filters in Python. One rule, two
        implementations — so they are checked against each other on the same ids."""
        indexer._store(self._rows())
        rows, _, _ = indexer.feed(limit=200, include_test=True)
        by_sql_hidden = {
            r["skill_id"] for r in rows
        } - {e["skill_id"] for e in client.get("/feed?limit=200").json()["events"]}
        assert by_sql_hidden == {s for s in JUNK_IDS if is_test_skill_id(s)}
        assert by_sql_hidden == set(JUNK_IDS)
