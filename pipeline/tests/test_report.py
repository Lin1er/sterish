"""Report publication and the evidence-hash reproducibility guarantee."""

import hashlib
from pathlib import Path

from sterish_pipeline.models import AuditReport, FinalVerdict
from sterish_pipeline.report import (
    canonical_report_bytes,
    evidence_hash_for,
    publish_report,
    verify_published_report,
)


def _report() -> AuditReport:
    return AuditReport(
        skill_id="com.x.demo",
        version="1.0.0",
        content_hash="a" * 64,
        final_verdict=FinalVerdict.SAFE,
        trust_score=90,
        recommendation="Safe to use.",
    )


class TestCanonicalBytes:
    def test_is_deterministic(self) -> None:
        assert canonical_report_bytes(_report()) == canonical_report_bytes(_report())

    def test_excludes_the_evidence_hash_field(self) -> None:
        # The hash must not depend on itself.
        r1 = _report()
        r2 = _report()
        r2.evidence_hash = "deadbeef"
        assert canonical_report_bytes(r1) == canonical_report_bytes(r2)

    def test_is_valid_utf8_json_with_trailing_newline(self) -> None:
        data = canonical_report_bytes(_report())
        assert data.endswith(b"\n")
        import json

        json.loads(data.decode("utf-8"))

    def test_field_change_changes_the_bytes(self) -> None:
        r = _report()
        r.trust_score = 50
        assert canonical_report_bytes(r) != canonical_report_bytes(_report())


class TestEvidenceHash:
    def test_matches_sha256_of_published_bytes(self) -> None:
        report = _report()
        expected = hashlib.sha256(canonical_report_bytes(report)).hexdigest()
        assert evidence_hash_for(report) == expected

    def test_is_64_lowercase_hex(self) -> None:
        digest = evidence_hash_for(_report())
        assert len(digest) == 64
        assert digest == digest.lower()
        int(digest, 16)  # parses as hex


class TestPublish:
    def test_writes_file_whose_hash_is_the_evidence_hash(self, tmp_path: Path) -> None:
        report = _report()
        path, uri, digest = publish_report(report, tmp_path)
        # The core promise: sha256(published file) == evidence_hash.
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert digest == evidence_hash_for(report)
        assert uri  # a fetchable location

    def test_base_uri_is_used_for_the_report_uri(self, tmp_path: Path) -> None:
        _, uri, _ = publish_report(_report(), tmp_path, base_uri="https://raw.example.com/reports/")
        assert uri == "https://raw.example.com/reports/com.x.demo@1.0.0.json"

    def test_verify_detects_tampering(self, tmp_path: Path) -> None:
        path, _, digest = publish_report(_report(), tmp_path)
        assert verify_published_report(path, digest) is True
        path.write_bytes(path.read_bytes() + b" tampered")
        assert verify_published_report(path, digest) is False

    def test_a_third_party_can_recompute_from_the_file(self, tmp_path: Path) -> None:
        path, _, digest = publish_report(_report(), tmp_path)
        # Simulate a reviewer with only the file and the on-chain hash.
        recomputed = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        assert recomputed == digest
