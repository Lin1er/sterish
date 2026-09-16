"""The LLM path, exercised entirely without an API key.

The whole suite must be green on a machine that has never seen an LLM key. Everything
below either injects a fake client or asserts on the no-key path; the two tests that need a
real key are marked ``skipif`` and are the only ones that would ever contact the network.
"""

import json
import os
from pathlib import Path

import pytest

from sterish_pipeline import llm as llm_module
from sterish_pipeline import run_audit
from sterish_pipeline.audit import _llm_will_be_attempted
from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.llm import (
    EMIT_VERDICT_TOOL,
    REPORT_INJECTION_TOOL,
    LLMUnavailable,
    api_key_present,
    build_synthesis_payload,
    load_prompt,
    parse_opinion,
    prompts_dir,
    synthesize_with_llm,
)
from sterish_pipeline.models import (
    FinalVerdict,
    Recommendation,
    Risk,
    SkillManifest,
    Stage1Result,
    Stage2Result,
    Verdict,
)

FIXTURES = Path(__file__).parent / "fixtures"
POISONED_PDF = FIXTURES / "poisoned_pdf_skill"
SAFE_SKILL = FIXTURES / "safe_skill"

KEY_VARS = ("LLM_API_KEY", "ANTHROPIC_API_KEY")
HAS_KEY = any(os.environ.get(v, "").strip() for v in KEY_VARS)
requires_key = pytest.mark.skipif(HAS_KEY is False, reason="no LLM key configured")


def no_key(monkeypatch) -> None:
    """Clear *every* key variable.

    Deleting only one used to be enough. With two backends it is not, and a test that
    clears one while the other is set in the shell passes for the wrong reason — the
    failure mode conftest.py already warns about elsewhere in this repo.
    """
    for name in KEY_VARS:
        monkeypatch.delenv(name, raising=False)


class FakeClient:
    """A structured client that answers whatever the test tells it to."""

    def __init__(self, answer=None, raises: Exception | None = None):
        self.answer = answer
        self.raises = raises
        self.calls: list[dict] = []

    def call_tool(self, system, payload, tool, config):
        self.calls.append({"system": system, "payload": payload, "tool": tool})
        if self.raises is not None:
            raise self.raises
        return self.answer


SAFE_ANSWER = {
    "verdict": "SAFE",
    "risk": "none",
    "score": 100,
    "recommendation": "ALLOW",
    "rationale": "Looks fine to me.",
}
DANGEROUS_ANSWER = {
    "verdict": "DANGEROUS",
    "risk": "critical",
    "score": 3,
    "recommendation": "BLOCK",
    "rationale": "The description tells the agent to read an SSH key.",
}


# ======================================================================================
# No key at all
# ======================================================================================
class TestFailSoftWithoutKey:
    def test_fail_soft_without_key(self, monkeypatch):
        no_key(monkeypatch)
        run = run_audit(POISONED_PDF)
        run.validate(submittable=True)
        assert run.report.llm_used is False
        assert run.report.llm_attempted is False
        assert run.document.verdict is Verdict.DANGEROUS

    def test_safe_fixture_stays_safe_without_key(self, monkeypatch):
        """No key must NOT be treated as an inconclusive LLM attempt, or every audit on a
        keyless machine would come out WARNING and the verdict would mean nothing."""
        no_key(monkeypatch)
        run = run_audit(SAFE_SKILL)
        assert run.document.verdict is Verdict.SAFE
        assert run.report.llm_attempted is False

    def test_note_explains_why_the_model_was_not_called(self, monkeypatch):
        no_key(monkeypatch)
        run = run_audit(SAFE_SKILL)
        assert any("LLM_API_KEY not set" in n for n in run.notes)

    def test_no_exception_is_raised_anywhere(self, monkeypatch):
        no_key(monkeypatch)
        for path in (POISONED_PDF, SAFE_SKILL, Path(__file__).parent / "poisoned_skill"):
            run_audit(path).validate()

    def test_api_key_present_reflects_the_environment(self, monkeypatch):
        no_key(monkeypatch)
        assert api_key_present() is False
        monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
        assert api_key_present() is False, "whitespace is not a key"
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value")
        assert api_key_present() is True

    def test_client_construction_refuses_without_a_key(self, monkeypatch):
        no_key(monkeypatch)
        with pytest.raises(LLMUnavailable):
            llm_module.AnthropicClient()

    def test_use_llm_false_short_circuits(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value")
        cfg = PipelineConfig(use_llm=False)
        client = FakeClient(answer=DANGEROUS_ANSWER)
        assert _llm_will_be_attempted(cfg, client) is False
        run = run_audit(SAFE_SKILL, cfg, llm_client=client)
        assert client.calls == []
        assert run.report.llm_used is False


# ======================================================================================
# The model is advisory: recorded, never merged (STE-39)
# ======================================================================================
def _document_bytes(run) -> bytes:
    from sterish_pipeline import reports

    return reports.canonical_bytes(run.verdict_json())


class TestLLMIsAdvisoryOnly:
    """Same bytes in, same document out — whatever the model says, or whether it answers."""

    def test_a_lenient_model_does_not_lower_a_dangerous_verdict(self):
        client = FakeClient(answer=SAFE_ANSWER)
        run = run_audit(POISONED_PDF, llm_client=client)
        assert client.calls, "the fake client must actually have been called"
        assert run.report.llm_used is True
        assert run.document.verdict is Verdict.DANGEROUS
        assert run.document.risk is Risk.CRITICAL
        assert run.document.recommendation is Recommendation.BLOCK
        assert run.document.score <= PipelineConfig().critical_max_score
        run.validate(submittable=True)

    def test_a_strict_model_does_not_raise_a_safe_verdict_either(self):
        """Until STE-39 this went DANGEROUS/3. A model that can raise the verdict is a
        model whose variance lands on chain."""
        baseline = run_audit(SAFE_SKILL, PipelineConfig(use_llm=False))
        run = run_audit(SAFE_SKILL, llm_client=FakeClient(answer=DANGEROUS_ANSWER))
        assert run.document.verdict is Verdict.SAFE
        assert run.document.score == baseline.document.score
        run.validate(submittable=True)

    def test_the_opinion_is_recorded_as_advisory_with_its_disagreement(self):
        run = run_audit(SAFE_SKILL, llm_client=FakeClient(answer=DANGEROUS_ANSWER))
        advisory = run.report.llm_advisory
        assert advisory is not None
        assert advisory.verdict is FinalVerdict.DANGEROUS
        assert advisory.score == 3
        assert advisory.stricter_than_verdict is True
        assert advisory.disagrees_with_verdict is True
        assert "SSH key" in advisory.rationale

    def test_an_agreeing_opinion_is_marked_as_agreeing(self):
        run = run_audit(SAFE_SKILL, llm_client=FakeClient(answer=SAFE_ANSWER))
        assert run.report.llm_advisory.disagrees_with_verdict is False
        assert run.report.llm_advisory.stricter_than_verdict is False

    def test_a_lenient_opinion_is_a_disagreement_but_not_stricter(self):
        run = run_audit(POISONED_PDF, llm_client=FakeClient(answer=SAFE_ANSWER))
        assert run.report.llm_advisory.disagrees_with_verdict is True
        assert run.report.llm_advisory.stricter_than_verdict is False

    def test_the_rationale_never_reaches_the_document_or_the_reasons(self):
        run = run_audit(SAFE_SKILL, llm_client=FakeClient(answer=DANGEROUS_ANSWER))
        assert "SSH key" not in json.dumps(run.verdict_json())
        assert not any("SSH key" in reason for reason in run.report.policy_reasons)

    @pytest.mark.parametrize(
        "client",
        [
            FakeClient(answer=SAFE_ANSWER),
            FakeClient(answer=DANGEROUS_ANSWER),
            FakeClient(answer={"verdict": "MALICIOUS"}),
            FakeClient(raises=TimeoutError("gateway timed out")),
            None,
        ],
        ids=["lenient", "strict", "invalid", "timeout", "no-model"],
    )
    @pytest.mark.parametrize("fixture", [SAFE_SKILL, POISONED_PDF], ids=["safe", "poisoned"])
    def test_the_published_bytes_do_not_depend_on_the_model(self, fixture, client):
        """The reproduction promise, stated as a test: the document — and so the
        evidence_hash on chain — is byte-identical with or without a model, and whatever
        the model answered."""
        reference = run_audit(fixture, PipelineConfig(use_llm=False))
        if client is None:
            run = run_audit(fixture, PipelineConfig(use_llm=False))
        else:
            run = run_audit(fixture, llm_client=client)
        assert _document_bytes(run) == _document_bytes(reference)
        assert run.document.evidence_hash == reference.document.evidence_hash

    def test_the_llm_trail_is_excluded_from_evidence_hash(self):
        from sterish_pipeline.stages.stage3_verdict_synthesis import (
            LLM_TRAIL_FIELDS,
            compute_evidence_hash,
        )

        run = run_audit(SAFE_SKILL, llm_client=FakeClient(answer=DANGEROUS_ANSWER))
        before = compute_evidence_hash(run.report)
        run.report.llm_notes = ["something entirely different"]
        run.report.llm_model = "another-model"
        run.report.llm_advisory = None
        run.report.llm_used = False
        run.report.llm_attempted = False
        assert compute_evidence_hash(run.report) == before
        assert LLM_TRAIL_FIELDS == {
            "llm_used", "llm_attempted", "llm_model", "llm_notes", "llm_advisory",
        }

    def test_everything_else_is_still_hashed(self):
        from sterish_pipeline.stages.stage3_verdict_synthesis import compute_evidence_hash

        run = run_audit(SAFE_SKILL, PipelineConfig(use_llm=False))
        before = compute_evidence_hash(run.report)
        run.report.policy_reasons = [*run.report.policy_reasons, "tampered"]
        assert compute_evidence_hash(run.report) != before


# ======================================================================================
# Failure modes, all fail-soft
# ======================================================================================
class TestFailureModes:
    @pytest.mark.parametrize(
        "answer",
        [
            {},
            {"verdict": "MALICIOUS", "risk": "high", "score": 1,
             "recommendation": "BLOCK", "rationale": "x"},
            {"verdict": "SAFE", "risk": "extreme", "score": 1,
             "recommendation": "ALLOW", "rationale": "x"},
            {"verdict": "SAFE", "risk": "none", "score": 101,
             "recommendation": "ALLOW", "rationale": "x"},
            {"verdict": "SAFE", "risk": "none", "score": -1,
             "recommendation": "ALLOW", "rationale": "x"},
            {"verdict": "SAFE", "risk": "none", "score": 90,
             "recommendation": "MAYBE", "rationale": "x"},
            {"verdict": "SAFE", "risk": "none", "score": 90,
             "recommendation": "ALLOW", "rationale": "   "},
            {"verdict": "SAFE", "risk": "none", "score": "high",
             "recommendation": "ALLOW", "rationale": "x"},
        ],
    )
    def test_invalid_answers_are_rejected(self, answer):
        with pytest.raises(LLMUnavailable):
            parse_opinion(answer, "claude-sonnet-5")

    def test_invalid_answer_leaves_the_verdict_alone(self):
        """Until STE-39 an attempted-but-inconclusive model forced WARNING (policy row 5).
        Whether a gateway answered is a fact about the auditor's network, not the skill."""
        run = run_audit(SAFE_SKILL, llm_client=FakeClient(answer={"verdict": "MALICIOUS"}))
        assert run.report.llm_used is False
        assert run.report.llm_attempted is True
        assert run.report.llm_advisory is None
        assert run.document.verdict is Verdict.SAFE
        assert run.document.recommendation is Recommendation.ALLOW
        run.validate()

    def test_exception_falls_back_to_the_baseline(self):
        run = run_audit(
            POISONED_PDF, llm_client=FakeClient(raises=TimeoutError("connection timed out"))
        )
        assert run.report.llm_used is False
        assert run.document.verdict is Verdict.DANGEROUS
        assert any("TimeoutError" in n for n in run.notes)
        run.validate()

    def test_failure_never_downgrades_a_dangerous_verdict(self):
        run = run_audit(POISONED_PDF, llm_client=FakeClient(raises=RuntimeError("boom")))
        assert run.document.verdict is Verdict.DANGEROUS
        assert run.document.risk is Risk.CRITICAL

    def test_notes_explain_the_failure(self):
        _, notes = synthesize_with_llm(
            SkillManifest(skill_id="com.example.skill", name="x", description="y",
                          version="1.0.0"),
            Stage1Result(),
            Stage2Result(),
            "SAFE", "none", 100, "ALLOW",
            client=FakeClient(raises=ValueError("bad json")),
        )
        assert any("ValueError" in n for n in notes)


# ======================================================================================
# Prompts and payloads
# ======================================================================================
class TestPrompts:
    def test_prompt_files_exist_on_disk(self):
        assert (prompts_dir() / "stage1_injection_scan.md").is_file()
        assert (prompts_dir() / "stage3_synthesis.md").is_file()
        assert (prompts_dir() / "README.md").is_file()

    def test_prompts_are_read_from_disk_not_hardcoded(self):
        source = Path(llm_module.__file__).read_text()
        assert "ignore all previous instructions" not in source.lower()
        assert 'load_prompt("stage3_synthesis")' in source

    def test_missing_prompt_raises_llm_unavailable(self):
        with pytest.raises(LLMUnavailable):
            load_prompt("no_such_prompt")

    def test_synthesis_prompt_states_the_model_is_advisory_only(self):
        text = load_prompt("stage3_synthesis").lower()
        assert "advisory and recorded, never merged" in text
        assert "not upward, not downward" in text

    def test_synthesis_prompt_says_markdown_skills_have_no_declaration_surface(self):
        """STE-39 part A: the model downgraded two catalogue skills "while declaring no
        permissions or tools" — the category error STE-36 removed from the regexes."""
        text = load_prompt("stage3_synthesis").lower()
        assert "published as markdown has nowhere to declare anything" in text
        assert "absence of declared permissions or tools is then not a" in " ".join(text.split())

    def test_prompt_is_sent_as_the_system_message(self):
        client = FakeClient(answer=DANGEROUS_ANSWER)
        run_audit(SAFE_SKILL, llm_client=client)
        assert client.calls[0]["system"] == load_prompt("stage3_synthesis")


class TestToolSchemas:
    @pytest.mark.parametrize("tool", [EMIT_VERDICT_TOOL, REPORT_INJECTION_TOOL])
    def test_tools_are_strict(self, tool):
        assert tool["strict"] is True
        assert tool["input_schema"]["additionalProperties"] is False
        assert tool["input_schema"]["required"]

    def test_verdict_tool_enums_match_the_frozen_vocabulary(self):
        props = EMIT_VERDICT_TOOL["input_schema"]["properties"]
        assert set(props["verdict"]["enum"]) == {"SAFE", "WARNING", "DANGEROUS"}
        assert set(props["risk"]["enum"]) == {v.value for v in Risk}
        assert set(props["recommendation"]["enum"]) == {v.value for v in Recommendation}
        assert props["score"]["maximum"] == 100

    def test_injection_tool_enum_matches_the_detectors(self):
        from sterish_pipeline.stages import injection_rules

        enum = set(
            REPORT_INJECTION_TOOL["input_schema"]["properties"]["findings"]["items"][
                "properties"
            ]["pattern_id"]["enum"]
        )
        assert enum == set(injection_rules.ALL_PATTERN_IDS) | {"other"}


class TestSynthesisPayload:
    def test_payload_carries_the_evidence_the_prompt_promises(self):
        run = run_audit(POISONED_PDF, llm_client=FakeClient(answer=DANGEROUS_ANSWER))
        payload = run.report  # sanity: the run completed
        assert payload is not None

        client = FakeClient(answer=DANGEROUS_ANSWER)
        run_audit(POISONED_PDF, llm_client=client)
        sent = client.calls[0]["payload"]
        assert sent["skill_id"] == "com.pdftools.summarizer"
        assert sent["baseline"]["verdict"] == "DANGEROUS"
        assert sent["stage1"]["injection_findings"]
        assert "manifest" in sent and "tools" in sent["manifest"]

    def test_payload_is_json_serializable(self):
        payload = build_synthesis_payload(
            SkillManifest(skill_id="com.example.skill", name="n", description="d",
                          version="1.0.0"),
            Stage1Result(),
            Stage2Result(),
            "SAFE", "none", 100, "ALLOW",
        )
        assert json.loads(json.dumps(payload))["baseline"]["score"] == 100

    def test_payload_is_deterministic(self):
        args = (
            SkillManifest(skill_id="com.example.skill", name="n", description="d",
                          version="1.0.0"),
            Stage1Result(),
            Stage2Result(),
            "SAFE", "none", 100, "ALLOW",
        )
        assert build_synthesis_payload(*args) == build_synthesis_payload(*args)


class TestParseOpinion:
    def test_valid_answer_parses(self):
        opinion = parse_opinion(DANGEROUS_ANSWER, "claude-sonnet-5")
        assert opinion.verdict is FinalVerdict.DANGEROUS
        assert opinion.risk is Risk.CRITICAL
        assert opinion.recommendation is Recommendation.BLOCK
        assert opinion.score == 3
        assert opinion.model == "claude-sonnet-5"

    def test_unaudited_is_not_an_acceptable_answer(self):
        with pytest.raises(LLMUnavailable):
            parse_opinion({**SAFE_ANSWER, "verdict": "UNAUDITED"}, "claude-sonnet-5")


# ======================================================================================
# Live path -- skipped unless a real key is present. CI must be green without one.
# ======================================================================================
@requires_key
class TestLLMPathLive:
    def test_llm_path_poisoned_pdf_is_dangerous(self):
        run = run_audit(POISONED_PDF)
        assert run.report.llm_attempted is True
        assert run.document.verdict is Verdict.DANGEROUS
        run.validate(submittable=True)

    def test_llm_path_safe_skill_document_is_valid(self):
        run = run_audit(SAFE_SKILL)
        assert run.report.llm_attempted is True
        run.validate(submittable=True)
        assert run.document.verdict is not Verdict.UNAUDITED
