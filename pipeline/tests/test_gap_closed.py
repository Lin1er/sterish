"""The load-bearing tests for STE-14: the gap is real, and it is now closed.

`poisoned_pdf_skill` declares `capabilities: ["FILE_READ"]` and hides its instructions in
prose. The declared-capability scanner cannot see that by construction, so before this ticket
the pipeline called it SAFE. These tests pin both halves of that story so a future refactor
cannot quietly reopen it.
"""

import json
from pathlib import Path

import pytest

from sterish_pipeline import run_audit
from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import (
    AuditReport,
    Capability,
    FinalVerdict,
    Recommendation,
    Risk,
    SkillManifest,
    Stage1Result,
    Stage2Result,
    Verdict,
)
from sterish_pipeline.stages import policy
from sterish_pipeline.stages.stage1_desc_scanner import run_stage1, scan_description
from sterish_pipeline.stages.stage3_verdict_synthesis import synthesize_verdict

FIXTURES = Path(__file__).parent / "fixtures"
POISONED_PDF = FIXTURES / "poisoned_pdf_skill"
SAFE_SKILL = FIXTURES / "safe_skill"
TOKEN_DRAINER = Path(__file__).parent / "poisoned_skill"


def _manifest(directory: Path) -> SkillManifest:
    return SkillManifest.model_validate(
        json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    )


@pytest.fixture(scope="module")
def poisoned_pdf_run():
    return run_audit(POISONED_PDF)


@pytest.fixture(scope="module")
def safe_run():
    return run_audit(SAFE_SKILL)


@pytest.fixture(scope="module")
def token_drainer_run():
    return run_audit(TOKEN_DRAINER)


# ======================================================================================
# 1. The gap was real
# ======================================================================================
class TestDeterministicPathAloneWouldHaveMissedIt:
    """This is the "before" picture. If these assertions ever fail, the gap moved."""

    def test_deterministic_path_alone_would_have_missed_it(self):
        manifest = _manifest(POISONED_PDF)

        # The old scanner reads only tools[*].capabilities, which say FILE_READ and nothing
        # else -- so a skill telling the agent to exfiltrate ~/.ssh/id_rsa scores 97/100.
        old = scan_description(manifest)
        assert old.initial_score == 97, "declared-capability score for FILE_READ only"
        assert len(old.risk_flags) == 1
        assert old.risk_flags[0].capability is Capability.FILE_READ
        assert old.risk_flags[0].severity.value == "LOW"

        # ...and the old synthesis turns that score into SAFE.
        old_report = synthesize_verdict(
            AuditReport(skill_id=manifest.skill_id), old, Stage2Result(), PipelineConfig()
        )
        assert old_report.final_verdict is FinalVerdict.SAFE
        assert old_report.trust_score >= PipelineConfig().safe_threshold

    def test_old_scanner_reads_no_text_at_all(self):
        """Proof of the mechanism, not just of the number.

        Replacing the entire poisoned prose with an empty string leaves the old scanner's
        answer byte-identical -- it never looked at the text.
        """
        manifest = _manifest(POISONED_PDF)
        blanked = manifest.model_copy(deep=True)
        blanked.description = ""
        for tool in blanked.tools:
            tool.description = ""
        assert scan_description(manifest).model_dump() == scan_description(blanked).model_dump()

    def test_new_scanner_reads_the_text(self):
        """The same blanking changes the new stage-1 answer completely."""
        manifest = _manifest(POISONED_PDF)
        blanked = manifest.model_copy(deep=True)
        blanked.description = ""
        for tool in blanked.tools:
            tool.description = ""
        poisoned = run_stage1(manifest, PipelineConfig(), POISONED_PDF)
        clean = run_stage1(blanked, PipelineConfig())
        assert poisoned.initial_score == 0
        assert clean.initial_score == 97
        assert poisoned.injection_findings
        assert clean.injection_findings == []


# ======================================================================================
# 2. The gap is closed
# ======================================================================================
class TestPoisonedPdfSkillIsDangerous:
    def test_poisoned_pdf_skill_is_dangerous(self, poisoned_pdf_run):
        doc = poisoned_pdf_run.document
        assert doc.verdict is Verdict.DANGEROUS
        assert doc.risk is Risk.CRITICAL
        assert doc.recommendation is Recommendation.BLOCK
        assert doc.score <= PipelineConfig().critical_max_score

    def test_findings_name_the_patterns_that_fired(self, poisoned_pdf_run):
        """The document must say WHICH rule fired, not merely that something did."""
        text = " ".join(f.description for f in poisoned_pdf_run.document.findings)
        for pattern_id in (
            "hidden_block",
            "ignore_instructions",
            "credential_path",
            "exfiltration",
            "zero_width",
            "html_comment_directive",
            "undeclared_capability",
            "name_behaviour_mismatch",
        ):
            assert f"[{pattern_id}]" in text, f"{pattern_id} missing from findings"

    def test_evidence_points_at_the_poisoned_fields(self, poisoned_pdf_run):
        evidence = " ".join(f.evidence for f in poisoned_pdf_run.document.findings)
        assert "tools[0].description" in evidence
        assert "manifest.description" in evidence
        assert "SKILL.md" in evidence

    def test_document_reports_the_capabilities_the_prose_implies(self, poisoned_pdf_run):
        """The manifest declares FILE_READ only. The document must not repeat that lie."""
        caps = set(poisoned_pdf_run.document.capabilities)
        assert Capability.FILE_READ in caps
        assert Capability.SECRET_READ in caps
        assert Capability.NETWORK_OUTBOUND in caps
        assert Capability.ENV_READ in caps
        assert Capability.SECRET_READ not in _manifest(POISONED_PDF).declared_capabilities()

    def test_skill_md_injection_is_caught(self, poisoned_pdf_run):
        found = [
            f
            for f in poisoned_pdf_run.report.stage1.injection_findings
            if f.field_path == "SKILL.md"
        ]
        assert {f.pattern_id for f in found} >= {"html_comment_directive", "credential_path"}

    def test_critical_patterns_are_recorded(self, poisoned_pdf_run):
        criticals = policy.critical_findings(
            poisoned_pdf_run.report.stage1.injection_findings
        )
        assert {f.pattern_id for f in criticals} >= {
            "credential_path",
            "exfiltration",
            "hidden_block",
            "ignore_instructions",
            "zero_width",
        }


# ======================================================================================
# 3. No collateral damage
# ======================================================================================
class TestSafeSkillIsSafe:
    def test_safe_skill_is_safe(self, safe_run):
        doc = safe_run.document
        assert doc.verdict is Verdict.SAFE
        assert doc.recommendation is Recommendation.ALLOW
        assert doc.risk in (Risk.NONE, Risk.LOW)
        assert doc.score >= PipelineConfig().safe_threshold

    def test_safe_skill_has_no_injection_findings(self, safe_run):
        assert safe_run.report.stage1.injection_findings == []

    def test_safe_skill_scanned_its_text(self, safe_run):
        # A zero-finding result is only meaningful if the scanner actually looked.
        assert safe_run.report.stage1.text_scanned >= 6

    def test_safe_skill_capabilities_match_the_manifest(self, safe_run):
        assert set(safe_run.document.capabilities) == {Capability.NETWORK_OUTBOUND}

    def test_declared_endpoint_is_not_an_exfiltration_finding(self, safe_run):
        assert "evil" not in json.dumps(safe_run.verdict_json())
        assert not [
            f
            for f in safe_run.report.stage1.injection_findings
            if f.pattern_id == "exfiltration"
        ]


class TestTokenDrainerStillDangerous:
    """The pre-existing fixture must not regress: it was already caught, it stays caught."""

    def test_token_drainer_still_dangerous(self, token_drainer_run):
        doc = token_drainer_run.document
        assert doc.verdict is Verdict.DANGEROUS
        assert doc.recommendation is Recommendation.BLOCK
        assert doc.risk is Risk.CRITICAL

    def test_token_drainer_declared_path_still_catches_it(self):
        """Unlike the pdf fixture, the OLD path alone already flagged this one."""
        old = scan_description(_manifest(TOKEN_DRAINER))
        assert old.initial_score < 30

    def test_token_drainer_content_hash_matches_the_chain(self, token_drainer_run):
        # Same value as docs/deployments.md and the frozen vector `poisoned-token-drainer`.
        assert token_drainer_run.content_hash == (
            "c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0"
        )

    def test_wallet_op_fires_on_the_drainer(self, token_drainer_run):
        ids = {f.pattern_id for f in token_drainer_run.report.stage1.injection_findings}
        assert "wallet_op" in ids


# ======================================================================================
# 4. Determinism
# ======================================================================================
class TestDeterminism:
    def test_same_input_same_document(self):
        a = run_audit(POISONED_PDF)
        b = run_audit(POISONED_PDF)
        assert a.verdict_json() == b.verdict_json()

    def test_manifest_path_and_directory_agree(self):
        by_dir = run_audit(POISONED_PDF)
        by_file = run_audit(POISONED_PDF / "manifest.json")
        assert by_dir.verdict_json() == by_file.verdict_json()

    def test_missing_manifest_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            run_audit(tmp_path)


class TestStage1Merge:
    def test_run_stage1_keeps_declared_flags_and_adds_injection_findings(self):
        result = run_stage1(_manifest(POISONED_PDF), PipelineConfig(), POISONED_PDF)
        assert result.risk_flags, "declared-capability path must still contribute"
        assert result.injection_findings, "text path must contribute"
        assert result.text_scanned == 7

    def test_reasoning_mentions_every_pattern(self):
        result = run_stage1(_manifest(POISONED_PDF), PipelineConfig(), POISONED_PDF)
        for pattern_id in {f.pattern_id for f in result.injection_findings}:
            assert pattern_id in result.reasoning

    def test_injection_deduction_is_heavier_than_declared_deduction(self):
        cfg = PipelineConfig()
        assert cfg.injection_high_deduction > cfg.high_risk_deduction

    def test_medium_only_findings_reduce_but_do_not_zero_the_score(self):
        cfg = PipelineConfig()
        stage1 = Stage1Result(initial_score=100)
        assert policy.injection_deduction(stage1.injection_findings, cfg) == 0
