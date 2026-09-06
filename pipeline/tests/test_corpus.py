"""Corpus store: snapshot integrity, provenance, and third-party reproduction.

The committed corpus is exercised end-to-end here — this is the test that proves
a third party can clone the repo and recompute every hash from the bytes.
"""

from datetime import UTC, datetime
from pathlib import Path

from sterish_pipeline.audit import audit_normalized
from sterish_pipeline.content_hash import content_hash
from sterish_pipeline.intake.corpus import Corpus, Provenance
from sterish_pipeline.intake.normalize import SourceKind
from sterish_pipeline.models import FinalVerdict

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"


def _corpus() -> Corpus:
    return Corpus(CORPUS_DIR)


class TestCommittedCorpus:
    """These run against the corpus that ships in the repo."""

    def test_index_exists(self) -> None:
        assert _corpus().index_path.exists(), "run scripts/build_fixture_corpus.py"

    def test_has_at_least_twelve_auditable_entries(self) -> None:
        # SOW D2: 10+ real catalog skills. 12+ total with 2+ poisoned.
        entries = _corpus().load()
        assert len(entries) >= 12

    def test_has_at_least_ten_real_catalog_skills(self) -> None:
        catalog = [e for e in _corpus().load() if e.label == "catalog"]
        assert len(catalog) >= 10

    def test_has_at_least_two_poisoned_fixtures(self) -> None:
        poisoned = [e for e in _corpus().load() if e.is_poisoned]
        assert len(poisoned) >= 2

    def test_every_entry_has_provenance(self) -> None:
        for entry in _corpus().load():
            assert entry.provenance.source
            assert entry.provenance.source_url

    def test_hashes_recompute_from_bytes(self) -> None:
        # The reproducibility promise: index hashes == hashes of the bytes.
        problems = _corpus().verify_all()
        assert problems == [], "\n".join(problems)

    def test_third_party_can_recompute_a_hash_by_hand(self) -> None:
        corpus = _corpus()
        entry = corpus.load()[0]
        files = corpus.read_files(entry)
        assert content_hash(files) == entry.content_hash

    def test_no_poisoned_entry_audits_as_safe(self) -> None:
        corpus = _corpus()
        for entry in corpus.load():
            if not entry.is_poisoned:
                continue
            report = audit_normalized(corpus.normalized(entry), skip_sandbox=True)
            assert report.final_verdict != FinalVerdict.SAFE, entry.skill_id

    # Known false positive in STE-14's scanner, reported on that ticket. The
    # `wallet_op` detector is deliberately negation-blind (documented in
    # stages/injection_rules.py), so price-checker is graded DANGEROUS for the
    # sentence "it never touches a wallet, never signs anything, never moves
    # funds". Kept visible rather than papered over by editing the fixture or
    # relaxing its expected verdict: the fixture is a fair example of a benign
    # skill on a crypto platform, and that is the point of having it.
    #
    # This set is asserted exactly, so fixing the scanner makes this test fail
    # and forces the entry to be removed.
    KNOWN_SCANNER_FALSE_POSITIVES = {"com.fixtures.safe.price-checker"}

    def test_expected_verdicts_hold(self) -> None:
        corpus = _corpus()
        mismatched: set[str] = set()

        for entry in corpus.load():
            if not entry.expected_verdict:
                continue
            report = audit_normalized(corpus.normalized(entry), skip_sandbox=True)
            if report.final_verdict.value != entry.expected_verdict:
                mismatched.add(entry.skill_id)

        assert mismatched == self.KNOWN_SCANNER_FALSE_POSITIVES, (
            f"verdict mismatches changed: {sorted(mismatched)} "
            f"(known: {sorted(self.KNOWN_SCANNER_FALSE_POSITIVES)})"
        )

    def test_poisoned_fixtures_are_never_safe(self) -> None:
        """The claim that matters, and it holds for every poisoned entry."""
        corpus = _corpus()
        checked = 0
        for entry in corpus.load():
            if not entry.is_poisoned:
                continue
            report = audit_normalized(corpus.normalized(entry), skip_sandbox=True)
            assert report.final_verdict != FinalVerdict.SAFE, entry.skill_id
            checked += 1
        assert checked >= 2, "corpus must carry at least two poisoned entries"


class TestCorpusRoundTrip:
    """A temporary corpus, to exercise write/verify without touching the repo."""

    def test_write_verify_roundtrip(self, tmp_path: Path) -> None:
        corpus = Corpus(tmp_path)
        entry = corpus.write_entry(
            skill_id="com.test.demo",
            version="1.0.0",
            kind=SourceKind.AGENT_SKILL,
            files={"SKILL.md": b"# Demo\n\nA demo."},
            relative_path="entries/demo",
            provenance=Provenance(source="test", source_url="repo:test"),
            label="safe",
            expected_verdict="SAFE",
        )
        corpus.save_index([entry], datetime.now(UTC).isoformat())
        assert corpus.verify_all() == []

    def test_tampering_is_detected(self, tmp_path: Path) -> None:
        corpus = Corpus(tmp_path)
        entry = corpus.write_entry(
            skill_id="com.test.demo",
            version="1.0.0",
            kind=SourceKind.AGENT_SKILL,
            files={"SKILL.md": b"original"},
            relative_path="entries/demo",
            provenance=Provenance(source="test"),
        )
        corpus.save_index([entry], datetime.now(UTC).isoformat())
        # Rewrite the snapshot bytes behind the index's back.
        (tmp_path / "entries" / "demo" / "SKILL.md").write_bytes(b"tampered")
        problems = corpus.verify_all()
        assert any("content_hash mismatch" in p for p in problems)

    def test_binary_write_preserves_crlf(self, tmp_path: Path) -> None:
        corpus = Corpus(tmp_path)
        corpus.write_entry(
            skill_id="com.test.eol",
            version="1.0.0",
            kind=SourceKind.AGENT_SKILL,
            files={"a.txt": b"line1\r\nline2\r\n"},
            relative_path="entries/eol",
            provenance=Provenance(source="test"),
        )
        written = (tmp_path / "entries" / "eol" / "a.txt").read_bytes()
        assert written == b"line1\r\nline2\r\n"

    def test_duplicate_skill_id_is_reported(self, tmp_path: Path) -> None:
        corpus = Corpus(tmp_path)
        e1 = corpus.write_entry(
            skill_id="dup",
            version="1",
            kind=SourceKind.AGENT_SKILL,
            files={"a": b"x"},
            relative_path="e1",
            provenance=Provenance(source="t"),
        )
        e2 = corpus.write_entry(
            skill_id="dup",
            version="2",
            kind=SourceKind.AGENT_SKILL,
            files={"a": b"y"},
            relative_path="e2",
            provenance=Provenance(source="t"),
        )
        corpus.save_index([e1, e2], datetime.now(UTC).isoformat())
        assert any("duplicate skill_id" in p for p in corpus.verify_all())
