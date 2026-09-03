"""The pipeline's real output, validated against the FROZEN artifacts.

This is the most objective gate in STE-14: not "the code looks right" but "the document this
pipeline actually emitted is accepted by docs/specs/verdict.schema.json, and its content_hash
is byte-identical to the frozen reference implementation's answer for the same directory".
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sterish_pipeline import run_audit, specs
from sterish_pipeline.models import Verdict, to_verdict_json

FIXTURES = Path(__file__).parent / "fixtures"
SKILL_DIRS = {
    "safe_skill": FIXTURES / "safe_skill",
    "poisoned_pdf_skill": FIXTURES / "poisoned_pdf_skill",
    "token_drainer": Path(__file__).parent / "poisoned_skill",
}


@pytest.fixture(scope="module")
def runs():
    return {name: run_audit(path) for name, path in SKILL_DIRS.items()}


class TestSchemaValidation:
    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_verdict_json_validates_against_frozen_schema(self, name, runs):
        document = runs[name].verdict_json()
        error = specs.schema_error(document)
        assert error is None, f"{name}: {error}\n{json.dumps(document, indent=2)[:2000]}"

    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_document_is_submittable(self, name, runs):
        # The pipeline may never emit UNAUDITED, so every real document must also pass the
        # stricter profile the on-chain submitter validates against.
        assert runs[name].document.verdict is not Verdict.UNAUDITED
        assert specs.schema_error(runs[name].verdict_json(), submittable=True) is None

    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_run_validate_helper_does_not_raise(self, name, runs):
        runs[name].validate(submittable=True)

    def test_json_round_trips_through_a_file(self, runs, tmp_path):
        path = tmp_path / "verdict.json"
        path.write_text(json.dumps(runs["poisoned_pdf_skill"].verdict_json(), indent=2))
        assert specs.schema_error(json.loads(path.read_text())) is None

    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_no_extra_properties_leak_in(self, name, runs):
        allowed = {
            "spec_version", "skill_id", "version", "content_hash", "verdict", "risk",
            "score", "capabilities", "findings", "recommendation", "evidence_hash",
        }
        document = runs[name].verdict_json()
        assert set(document) == allowed
        for finding in document["findings"]:
            assert set(finding) <= {
                "stage", "capability", "severity", "description", "evidence"
            }

    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_no_llm_metadata_reaches_the_document(self, name, runs):
        """The audit trail (model id, notes, key) lives in the internal report only.

        Matched on identifiers, not on the English word "model": a finding is allowed to say
        "invisible text reaches the model but not the reviewer" -- that is prose about the
        attack, not leaked metadata.
        """
        blob = json.dumps(runs[name].verdict_json()).lower()
        for leak in ("llm_", "anthropic", "api_key", "sk-ant", "claude-", "llm_notes",
                     "llm_model", "rationale"):
            assert leak not in blob, f"{leak!r} leaked into the verdict document"
        assert "llm_notes" not in runs[name].verdict_json()

    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_internal_report_keeps_the_audit_trail(self, name, runs):
        report = runs[name].report
        assert isinstance(report.llm_notes, list) and report.llm_notes
        assert report.policy_reasons


class TestContentHash:
    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_content_hash_matches_frozen_reference(self, name, runs):
        expected = specs.content_hash_module().hash_dir(SKILL_DIRS[name])
        assert runs[name].document.content_hash == expected
        assert runs[name].content_hash == expected

    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_content_hash_matches_the_reference_cli(self, name, runs):
        """Independent check: run the frozen script as a subprocess, exactly as a reviewer
        would, and compare its stdout."""
        script = specs.repo_root() / "docs/specs/reference/content_hash.py"
        out = subprocess.run(
            [sys.executable, str(script), str(SKILL_DIRS[name])],
            capture_output=True,
            text=True,
            check=True,
        )
        assert out.stdout.strip() == runs[name].document.content_hash

    def test_token_drainer_hash_is_the_frozen_vector(self, runs):
        vectors = json.loads(
            (specs.repo_root() / "docs/specs/vectors/content-hash-vectors.json").read_text()
        )
        pinned = next(
            v["expected_sha256"]
            for v in vectors["vectors"]
            if v["id"] == "poisoned-token-drainer"
        )
        assert runs["token_drainer"].document.content_hash == pinned

    def test_editing_one_byte_changes_the_hash(self, tmp_path):
        src = SKILL_DIRS["safe_skill"]
        dst = tmp_path / "copy"
        dst.mkdir()
        for f in src.iterdir():
            (dst / f.name).write_bytes(f.read_bytes())
        before = run_audit(dst).content_hash
        manifest = json.loads((dst / "manifest.json").read_text())
        manifest["description"] += "."
        (dst / "manifest.json").write_text(json.dumps(manifest))
        assert run_audit(dst).content_hash != before


class TestEvidenceHash:
    def test_evidence_hash_covers_the_findings(self, runs):
        """Regression for verdict-json.md gap P8: the old hash anchored five numbers, so
        rewriting a finding left it unchanged."""
        run = runs["poisoned_pdf_skill"]
        before = run.report.evidence_hash
        mutated = run.report.model_copy(deep=True)
        mutated.findings[0].description = "something else entirely"
        from sterish_pipeline.stages.stage3_verdict_synthesis import compute_evidence_hash

        assert compute_evidence_hash(mutated) != before

    def test_evidence_hash_is_reproducible(self, runs):
        from sterish_pipeline.stages.stage3_verdict_synthesis import compute_evidence_hash

        run = runs["safe_skill"]
        assert compute_evidence_hash(run.report) == run.report.evidence_hash

    def test_evidence_hash_is_64_lowercase_hex(self, runs):
        for run in runs.values():
            h = run.document.evidence_hash
            assert len(h) == 64 and h == h.lower()

    def test_different_skills_have_different_evidence_hashes(self, runs):
        hashes = {run.document.evidence_hash for run in runs.values()}
        assert len(hashes) == len(runs)


class TestDocumentConventions:
    """Relations the schema deliberately does not enforce, checked here instead
    (verdict-json.md §4.1)."""

    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_verdict_and_recommendation_agree(self, name, runs):
        doc = runs[name].document
        expected = {"SAFE": "ALLOW", "WARNING": "REVIEW", "DANGEROUS": "BLOCK"}
        assert doc.recommendation.value == expected[doc.verdict.value]

    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_every_finding_has_checkable_evidence(self, name, runs):
        for finding in runs[name].document.findings:
            assert finding.evidence.strip()
            assert finding.description.strip()

    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_finding_capabilities_are_listed_in_capabilities(self, name, runs):
        doc = runs[name].document
        attributed = {f.capability for f in doc.findings if f.capability is not None}
        assert attributed <= set(doc.capabilities)

    @pytest.mark.parametrize("name", sorted(SKILL_DIRS))
    def test_stages_are_in_range(self, name, runs):
        assert {f.stage for f in runs[name].document.findings} <= {1, 2, 3}

    def test_identity_fields_come_from_the_manifest(self, runs):
        run = runs["safe_skill"]
        assert run.document.skill_id == run.manifest.skill_id == "com.sterish.weather-lookup"
        assert run.document.version == run.manifest.version == "1.0.0"

    def test_spec_version_is_1_0_0(self, runs):
        assert all(r.document.spec_version == "1.0.0" for r in runs.values())

    def test_to_verdict_json_is_the_serializer(self, runs):
        run = runs["safe_skill"]
        assert to_verdict_json(run.document) == run.verdict_json()
