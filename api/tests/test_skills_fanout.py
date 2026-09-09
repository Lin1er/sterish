"""`/skills` and `/skills/{id}` read their rows concurrently (STE-33).

The behaviour under test is a performance property, so these assert the two things
that make it observable without a network: the reads overlap, and the page survives a
row that cannot be read. Response shape is unchanged and is covered by test_routes.py.
"""

import threading
import time

from sterish_api import chain
from sterish_api.config import settings
from tests.conftest import SAFE_RECORD


def _entries(count: int) -> list[dict]:
    return [
        {
            "skill_id": f"com.acme.skill-{n}",
            "owner": "G" + "A" * 55,
            "versions": ["1.0.0"],
            "latest_version": "1.0.0",
            "latest_audited_version": "1.0.0",
            "registered_at": 1_756_800_000 + n,
        }
        for n in range(count)
    ]


class TestListSkills:
    def test_row_reads_overlap(self, client, monkeypatch):
        """20 rows x 50ms is 1.0s serially. This is the 9.9s-for-20-rows measurement."""
        monkeypatch.setattr(chain, "query_all_skills", lambda start, limit: _entries(20))
        monkeypatch.setattr(chain, "get_skill_count", lambda: 20)

        def slow_read(skill_id, version):
            time.sleep(0.05)
            return dict(SAFE_RECORD, skill_id=skill_id, version=version)

        monkeypatch.setattr(chain, "get_version", slow_read)

        started = time.monotonic()
        r = client.get("/skills?limit=20")
        elapsed = time.monotonic() - started

        assert r.status_code == 200
        assert len(r.json()["skills"]) == 20
        assert elapsed < 0.6, f"took {elapsed:.2f}s; rows were still read in series"

    def test_never_exceeds_the_configured_concurrency(self, client, monkeypatch):
        """A page of 100 must not open 100 sockets to the public RPC node at once."""
        monkeypatch.setattr(chain, "query_all_skills", lambda start, limit: _entries(100))
        monkeypatch.setattr(chain, "get_skill_count", lambda: 100)

        in_flight = 0
        peak = 0
        lock = threading.Lock()

        def tracked(skill_id, version):
            nonlocal in_flight, peak
            with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            time.sleep(0.01)
            with lock:
                in_flight -= 1
            return dict(SAFE_RECORD, skill_id=skill_id, version=version)

        monkeypatch.setattr(chain, "get_version", tracked)
        assert client.get("/skills?limit=100").status_code == 200
        assert peak <= settings.chain_concurrency

    def test_rows_stay_matched_to_their_skill(self, client, monkeypatch):
        """Concurrency must not shuffle verdicts onto the wrong row.

        Staggered delays would surface a completion-ordered zip immediately.
        """
        monkeypatch.setattr(chain, "query_all_skills", lambda start, limit: _entries(12))
        monkeypatch.setattr(chain, "get_skill_count", lambda: 12)

        def scored(skill_id, version):
            n = int(skill_id.rsplit("-", 1)[1])
            time.sleep((12 - n) * 0.005)
            return dict(SAFE_RECORD, skill_id=skill_id, version=version, trust_score=n)

        monkeypatch.setattr(chain, "get_version", scored)

        rows = client.get("/skills?limit=12").json()["skills"]
        assert [row["skill_id"] for row in rows] == [e["skill_id"] for e in _entries(12)]
        # Each row carries its OWN score, not a neighbour's.
        for n, row in enumerate(rows):
            assert row["latest_audited_trust_score"] == n

    def test_one_unreadable_row_does_not_fail_the_page(self, client, monkeypatch):
        """The pre-existing ContractError policy: skip the row, keep the page."""
        monkeypatch.setattr(chain, "query_all_skills", lambda start, limit: _entries(5))
        monkeypatch.setattr(chain, "get_skill_count", lambda: 5)

        def one_bad(skill_id, version):
            if skill_id.endswith("-2"):
                raise chain.ContractError(4)
            return dict(SAFE_RECORD, skill_id=skill_id, version=version)

        monkeypatch.setattr(chain, "get_version", one_bad)

        rows = client.get("/skills?limit=5").json()["skills"]
        assert len(rows) == 5
        assert rows[2]["latest_audited_verdict"] is None
        assert rows[2]["latest_audited_is_verified"] is None
        assert rows[2]["skill_id"] == "com.acme.skill-2"  # still listed
        assert rows[0]["latest_audited_verdict"] == "SAFE"

    def test_unaudited_rows_never_reach_the_chain(self, client, monkeypatch):
        """A row with no audited version has nothing to read; don't spend an RPC on it."""
        entries = _entries(3)
        for entry in entries:
            entry["latest_audited_version"] = None
        monkeypatch.setattr(chain, "query_all_skills", lambda start, limit: entries)
        monkeypatch.setattr(chain, "get_skill_count", lambda: 3)

        calls = []
        monkeypatch.setattr(
            chain, "get_version", lambda s, v: calls.append((s, v)) or SAFE_RECORD
        )

        rows = client.get("/skills?limit=3").json()["skills"]
        assert calls == []
        assert all(row["latest_audited_verdict"] is None for row in rows)


class TestSkillDetail:
    def test_version_reads_overlap(self, client, monkeypatch):
        versions = [f"1.0.{n}" for n in range(20)]
        monkeypatch.setattr(chain, "query_skill", lambda s: {
            "skill_id": s, "owner": "G" + "A" * 55, "versions": versions,
            "latest_version": versions[-1], "latest_audited_version": versions[-1],
            "registered_at": 1,
        })

        def slow_read(skill_id, version):
            time.sleep(0.05)
            return dict(SAFE_RECORD, skill_id=skill_id, version=version)

        monkeypatch.setattr(chain, "get_version", slow_read)

        started = time.monotonic()
        body = client.get("/skills/com.acme.pdf-suite").json()
        elapsed = time.monotonic() - started

        assert len(body["audited_versions"]) == 20
        assert elapsed < 0.6, f"took {elapsed:.2f}s; versions were still read in series"

    def test_versions_keep_registry_order(self, client, monkeypatch):
        versions = [f"1.0.{n}" for n in range(10)]
        monkeypatch.setattr(chain, "query_skill", lambda s: {
            "skill_id": s, "owner": "G" + "A" * 55, "versions": versions,
            "latest_version": versions[-1], "latest_audited_version": versions[-1],
            "registered_at": 1,
        })

        def staggered(skill_id, version):
            n = int(version.rsplit(".", 1)[1])
            time.sleep((10 - n) * 0.005)
            return dict(SAFE_RECORD, skill_id=skill_id, version=version)

        monkeypatch.setattr(chain, "get_version", staggered)

        body = client.get("/skills/com.acme.pdf-suite").json()
        assert [v["version"] for v in body["audited_versions"]] == versions

    def test_one_unreadable_version_is_skipped_not_fatal(self, client, monkeypatch):
        versions = ["1.0.0", "1.0.1", "1.0.2"]
        monkeypatch.setattr(chain, "query_skill", lambda s: {
            "skill_id": s, "owner": "G" + "A" * 55, "versions": versions,
            "latest_version": "1.0.2", "latest_audited_version": "1.0.2",
            "registered_at": 1,
        })

        def one_bad(skill_id, version):
            if version == "1.0.1":
                raise chain.ContractError(4)
            return dict(SAFE_RECORD, skill_id=skill_id, version=version)

        monkeypatch.setattr(chain, "get_version", one_bad)

        body = client.get("/skills/com.acme.pdf-suite").json()
        assert [v["version"] for v in body["audited_versions"]] == ["1.0.0", "1.0.2"]

    def test_fan_out_stays_capped_at_fifty_versions(self, client, monkeypatch):
        """api-spec section 6: a skill with many versions must not stall the request."""
        versions = [f"1.0.{n}" for n in range(80)]
        monkeypatch.setattr(chain, "query_skill", lambda s: {
            "skill_id": s, "owner": "G" + "A" * 55, "versions": versions,
            "latest_version": versions[-1], "latest_audited_version": versions[-1],
            "registered_at": 1,
        })

        read = []
        lock = threading.Lock()

        def counted(skill_id, version):
            with lock:
                read.append(version)
            return dict(SAFE_RECORD, skill_id=skill_id, version=version)

        monkeypatch.setattr(chain, "get_version", counted)
        client.get("/skills/com.acme.pdf-suite")
        assert len(read) == 50
