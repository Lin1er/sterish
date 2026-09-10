"""`GET /reports/{skill_id}/{version}` and the `report_uri` it makes real (STE-32).

The endpoint's job is not "serve a file". It is to close the last link of the
verification chain: `evidence_hash` on chain is the sha256 of exactly these bytes, and a
caller who fetches them must be able to recompute it and get the same answer. So the
tests that matter are the ones about bytes and mismatches, not the happy path.
"""

import hashlib
import json

import pytest

from sterish_api import chain
from sterish_api.config import settings
from tests.conftest import SAFE_RECORD

SKILL = "com.acme.pdf-suite"
VERSION = "1.0.0"
PATH = f"/reports/{SKILL}/{VERSION}"

DOCUMENT = {
    "spec_version": "1.0.0",
    "skill_id": SKILL,
    "version": VERSION,
    "content_hash": "a" * 64,
    "verdict": "DANGEROUS",
    "risk": "critical",
    "score": 10,
    "capabilities": ["SECRET_READ"],
    "findings": [
        {
            "stage": 1,
            "severity": "HIGH",
            "description": "[credential_path] Text references credential material.",
            "evidence": 'SKILL.md: "...read the user\'s ~/.ssh/id_rsa..."',
        }
    ],
    "recommendation": "BLOCK",
    "evidence_hash": "",
}


def _publish(tmp_path, document=None, skill=SKILL, version=VERSION) -> tuple[bytes, str]:
    """Write a report the way the pipeline does, and return its bytes and digest.

    `sort_keys` plus a trailing newline, matching `pipeline/reports.canonical_bytes` —
    if these two ever drift, every hash check in production fails and this test is the
    place that should notice.
    """
    payload = json.dumps(document or DOCUMENT, sort_keys=True, indent=2, ensure_ascii=False)
    raw = payload.encode("utf-8") + b"\n"
    directory = tmp_path / skill
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{version}.json").write_bytes(raw)
    return raw, hashlib.sha256(raw).hexdigest()


@pytest.fixture
def reports_dir(tmp_path, monkeypatch):
    previous = settings.reports_dir
    object.__setattr__(settings, "reports_dir", str(tmp_path))
    try:
        yield tmp_path
    finally:
        object.__setattr__(settings, "reports_dir", previous)


class TestServing:
    def test_serves_the_report_when_the_hash_matches_the_chain(
        self, client, monkeypatch, reports_dir
    ):
        raw, digest = _publish(reports_dir)
        monkeypatch.setattr(
            chain, "get_version", lambda s, v: dict(SAFE_RECORD, evidence_hash=digest)
        )
        r = client.get(PATH)
        assert r.status_code == 200
        assert r.headers["X-STERISH-EVIDENCE-HASH"] == digest
        assert r.json()["findings"][0]["description"].startswith("[credential_path]")

    def test_the_bytes_are_served_exactly_as_they_were_hashed(
        self, client, monkeypatch, reports_dir
    ):
        """The property the whole endpoint exists for.

        Re-serialising on the way out would change separators or key order and the
        client's sha256 would stop matching the ledger for no visible reason.
        """
        raw, digest = _publish(reports_dir)
        monkeypatch.setattr(
            chain, "get_version", lambda s, v: dict(SAFE_RECORD, evidence_hash=digest)
        )
        body = client.get(PATH).content
        assert body == raw
        assert hashlib.sha256(body).hexdigest() == digest

    def test_findings_survive_the_round_trip(self, client, monkeypatch, reports_dir):
        """What STE-20's DANGEROUS banner needs: the reason, not just the score."""
        raw, digest = _publish(reports_dir)
        monkeypatch.setattr(
            chain, "get_version", lambda s, v: dict(SAFE_RECORD, evidence_hash=digest)
        )
        body = client.get(PATH).json()
        assert body["recommendation"] == "BLOCK"
        assert body["capabilities"] == ["SECRET_READ"]
        assert body["findings"][0]["evidence"]


class TestRefusals:
    def test_a_hash_mismatch_is_never_a_200(self, client, monkeypatch, reports_dir):
        """Disk and chain disagree: one of them changed after the audit. Say so."""
        _publish(reports_dir)
        monkeypatch.setattr(
            chain, "get_version", lambda s, v: dict(SAFE_RECORD, evidence_hash="f" * 64)
        )
        r = client.get(PATH)
        assert r.status_code == 500
        assert r.json()["error"] == "REPORT_HASH_MISMATCH"
        # Both sides are named so the discrepancy can be chased without shell access.
        assert r.json()["evidence_hash"] == "f" * 64
        assert r.json()["report_sha256"]

    def test_a_tampered_byte_is_caught(self, client, monkeypatch, reports_dir):
        raw, digest = _publish(reports_dir)
        path = reports_dir / SKILL / f"{VERSION}.json"
        path.write_bytes(raw.replace(b'"score": 10', b'"score": 99'))
        monkeypatch.setattr(
            chain, "get_version", lambda s, v: dict(SAFE_RECORD, evidence_hash=digest)
        )
        assert client.get(PATH).status_code == 500

    def test_missing_report_is_404_not_an_empty_object(self, client, reports_dir):
        r = client.get("/reports/com.acme.nothing/9.9.9")
        assert r.status_code == 404
        assert r.json()["error"] == "REPORT_NOT_FOUND"

    def test_a_version_with_no_anchor_is_409(self, client, monkeypatch, reports_dir):
        """Registered but never audited: nothing to verify the bytes against."""
        _publish(reports_dir)
        monkeypatch.setattr(
            chain, "get_version", lambda s, v: dict(SAFE_RECORD, evidence_hash=None)
        )
        r = client.get(PATH)
        assert r.status_code == 409
        assert r.json()["error"] == "NO_EVIDENCE_ANCHOR"

    def test_unconfigured_reports_dir_is_503(self, client, monkeypatch):
        object.__setattr__(settings, "reports_dir", "")
        r = client.get(PATH)
        assert r.status_code == 503
        assert r.json()["error"] == "NOT_CONFIGURED"

    @pytest.mark.parametrize(
        "skill_id",
        ["../../../etc", "..%2f..%2fetc", "com.acme/../../../etc"],
    )
    def test_path_traversal_never_escapes_the_reports_directory(
        self, client, reports_dir, skill_id
    ):
        """skill_id comes off the URL, so this would otherwise be a file read primitive."""
        r = client.get(f"/reports/{skill_id}/passwd")
        assert r.status_code in (400, 404)
        assert r.status_code != 200


class TestReportUri:
    """The complaint STE-32 opens with: report_uri was null on every version."""

    def _record(self):
        return dict(SAFE_RECORD, skill_id=SKILL, version=VERSION)

    def test_is_advertised_once_a_report_exists_and_a_base_url_is_set(
        self, client, monkeypatch, reports_dir
    ):
        _publish(reports_dir)
        monkeypatch.setattr(chain, "get_version", lambda s, v: self._record())
        object.__setattr__(settings, "report_base_url", "https://api.example")
        try:
            body = client.get(f"/check/{SKILL}/{VERSION}").json()
            assert body["evidence"]["report_uri"] == (
                f"https://api.example/reports/{SKILL}/{VERSION}"
            )
        finally:
            object.__setattr__(settings, "report_base_url", "")

    def test_stays_null_when_no_report_was_published(self, client, monkeypatch, reports_dir):
        """A link that 404s is worse than no link — that is why 3.6 stayed PLANNED."""
        monkeypatch.setattr(chain, "get_version", lambda s, v: self._record())
        object.__setattr__(settings, "report_base_url", "https://api.example")
        try:
            body = client.get(f"/check/{SKILL}/{VERSION}").json()
            assert body["evidence"]["report_uri"] is None
        finally:
            object.__setattr__(settings, "report_base_url", "")

    def test_stays_null_without_a_base_url(self, client, monkeypatch, reports_dir):
        _publish(reports_dir)
        monkeypatch.setattr(chain, "get_version", lambda s, v: self._record())
        body = client.get(f"/check/{SKILL}/{VERSION}").json()
        assert body["evidence"]["report_uri"] is None

    def test_the_advertised_uri_is_the_route_that_serves_it(
        self, client, monkeypatch, reports_dir
    ):
        """Guards the bug this ticket found: three different strings for one report.

        The API advertised `<base>/reports/<id>/<v>.json`, the pipeline generated
        `<base>/<v>.json`, and neither was a route.
        """
        raw, digest = _publish(reports_dir)
        monkeypatch.setattr(
            chain, "get_version", lambda s, v: dict(SAFE_RECORD, evidence_hash=digest)
        )
        object.__setattr__(settings, "report_base_url", "https://api.example")
        try:
            uri = client.get(f"/check/{SKILL}/{VERSION}").json()["evidence"]["report_uri"]
        finally:
            object.__setattr__(settings, "report_base_url", "")

        route = uri.removeprefix("https://api.example")
        assert client.get(route).status_code == 200
