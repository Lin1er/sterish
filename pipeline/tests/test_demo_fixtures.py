"""The STE-18 demo set: four skills that light all four registry states.

These fixtures exist to put SAFE, DANGEROUS, WARNING and UNAUDITED into the live
registry at the same time, so the dashboard renders real chain data rather than a
mock. Each one is pinned here to the exact policy row it is designed to reach —
a fixture that lands on WARNING by accident, through a different row, proves
nothing about the rule it was written to demonstrate.
"""

from pathlib import Path

import pytest

from sterish_pipeline.audit import audit_normalized
from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.intake.corpus import SEED_MODE_REGISTER_ONLY, Corpus
from sterish_pipeline.models import FinalVerdict, Severity
from sterish_pipeline.stages import policy

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"
DEMO_LABEL = "demo"

#: The four skill ids seeded by STE-18, and the version each one contributes.
DEMO_SKILLS = {
    "com.fixtures.demo.release-notes": ["1.0.0", "2.0.0"],
    "com.fixtures.demo.changelog-writer": ["1.0.0", "2.0.0"],
    "com.fixtures.demo.ledger-inspector": ["1.0.0"],
    "com.fixtures.demo.table-formatter": ["1.0.0"],
}


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return Corpus(CORPUS_DIR)


@pytest.fixture(scope="module")
def demo(corpus: Corpus) -> dict[tuple[str, str], object]:
    return {e.key: e for e in corpus.load() if e.label == DEMO_LABEL}


def _audit(corpus: Corpus, entry):
    return audit_normalized(
        corpus.normalized(entry), config=PipelineConfig(use_llm=False), skip_sandbox=True
    )


def test_exactly_four_demo_skill_ids(demo) -> None:
    assert {skill_id for skill_id, _ in demo} == set(DEMO_SKILLS)


def test_every_demo_version_is_present(demo) -> None:
    got: dict[str, list[str]] = {}
    for skill_id, version in demo:
        got.setdefault(skill_id, []).append(version)
    assert {k: sorted(v) for k, v in got.items()} == DEMO_SKILLS


def test_demo_namespace_is_not_a_test_namespace(demo) -> None:
    """These four must survive the API's test-namespace filter — being visible is
    the entire point of them."""
    from sterish_pipeline.namespaces import is_test_skill_id

    for skill_id, _ in demo:
        assert not is_test_skill_id(skill_id), skill_id


class TestRugPull:
    """One skill, two versions, verdicts differing. Invariant R4."""

    def test_v1_is_safe(self, corpus, demo) -> None:
        report = _audit(corpus, demo[("com.fixtures.demo.release-notes", "1.0.0")])
        assert report.final_verdict is FinalVerdict.SAFE
        assert not report.stage1.injection_findings

    def test_v2_is_dangerous_by_the_critical_override(self, corpus, demo) -> None:
        report = _audit(corpus, demo[("com.fixtures.demo.release-notes", "2.0.0")])
        assert report.final_verdict is FinalVerdict.DANGEROUS
        assert policy.critical_findings(report.stage1.injection_findings)
        assert any("policy row 1" in r for r in report.policy_reasons)

    def test_the_two_versions_are_different_bytes(self, demo) -> None:
        v1 = demo[("com.fixtures.demo.release-notes", "1.0.0")]
        v2 = demo[("com.fixtures.demo.release-notes", "2.0.0")]
        assert v1.content_hash != v2.content_hash
        # The badge is keyed on the hash, so a changed byte cannot inherit it.
        assert v1.skill_id == v2.skill_id


class TestStaleVersion:
    """One skill whose latest version was never audited."""

    def test_v1_is_audited_and_safe(self, corpus, demo) -> None:
        report = _audit(corpus, demo[("com.fixtures.demo.changelog-writer", "1.0.0")])
        assert report.final_verdict is FinalVerdict.SAFE

    def test_v2_is_register_only(self, demo) -> None:
        entry = demo[("com.fixtures.demo.changelog-writer", "2.0.0")]
        assert entry.seed_mode == SEED_MODE_REGISTER_ONLY
        assert entry.register_only is True

    def test_v2_declares_no_expected_verdict(self, demo) -> None:
        """The pipeline never emits UNAUDITED, so there is nothing to expect."""
        assert demo[("com.fixtures.demo.changelog-writer", "2.0.0")].expected_verdict == ""


class TestWarningRows:
    """WARNING is reachable two deterministic ways. One fixture proves each."""

    def test_row_8_score_in_the_grey_band_with_no_findings(self, corpus, demo) -> None:
        report = _audit(corpus, demo[("com.fixtures.demo.ledger-inspector", "1.0.0")])
        cfg = PipelineConfig()
        assert report.final_verdict is FinalVerdict.WARNING
        assert report.stage1.injection_findings == []
        assert cfg.warning_threshold <= report.trust_score < cfg.safe_threshold
        assert any("policy row 8" in r for r in report.policy_reasons)

    def test_row_6_a_non_critical_finding_at_an_otherwise_safe_score(
        self, corpus, demo
    ) -> None:
        report = _audit(corpus, demo[("com.fixtures.demo.table-formatter", "1.0.0")])
        cfg = PipelineConfig()
        findings = report.stage1.injection_findings
        assert report.final_verdict is FinalVerdict.WARNING
        assert findings, "row 6 needs at least one finding"
        assert not policy.critical_findings(findings)
        assert all(f.severity is not Severity.HIGH for f in findings), (
            "a HIGH finding would be caught by row 3 or 4, not row 6"
        )
        assert report.trust_score >= cfg.safe_threshold, (
            "the score must be one that would otherwise pass, or this is row 8 again"
        )
        assert any("policy row 6" in r for r in report.policy_reasons)

    def test_neither_warning_needs_a_model(self, corpus, demo) -> None:
        """Row 5 — the LLM-inconclusive row STE-39 removes — is not involved."""
        for skill_id in ("com.fixtures.demo.ledger-inspector",
                         "com.fixtures.demo.table-formatter"):
            report = _audit(corpus, demo[(skill_id, "1.0.0")])
            assert not report.llm_attempted
            assert not any("policy row 5" in r for r in report.policy_reasons)


def test_all_four_states_are_covered(corpus, demo) -> None:
    """The claim the demo set exists to make, asserted over the corpus itself."""
    verdicts = set()
    for entry in demo.values():
        if entry.register_only:
            verdicts.add("UNAUDITED")
            continue
        verdicts.add(_audit(corpus, entry).final_verdict.value)
    assert verdicts == {"SAFE", "DANGEROUS", "WARNING", "UNAUDITED"}
