"""The decision table in policy.py, row by row."""

import pytest

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import (
    AuditReport,
    BehavioralFlag,
    Capability,
    FinalVerdict,
    InjectionFinding,
    Recommendation,
    Risk,
    RiskFlag,
    Severity,
    Stage1Result,
    Stage2Result,
)
from sterish_pipeline.stages import policy
from sterish_pipeline.stages.stage3_verdict_synthesis import synthesize_verdict

CFG = PipelineConfig()


def _injection(pattern_id: str, severity: Severity = Severity.HIGH) -> InjectionFinding:
    return InjectionFinding(
        pattern_id=pattern_id,
        severity=severity,
        description="test finding",
        field_path="tools[0].description",
        snippet="...",
    )


class TestCriticalOverride:
    @pytest.mark.parametrize("pattern_id", sorted(policy.CRITICAL_PATTERNS))
    def test_critical_override_beats_high_score(self, pattern_id):
        """Row 1. A perfect component score loses to one critical finding."""
        stage1 = Stage1Result(initial_score=100, injection_findings=[_injection(pattern_id)])
        decision = policy.decide(stage1, Stage2Result(), 100, CFG)
        assert decision.verdict is FinalVerdict.DANGEROUS
        assert decision.risk is Risk.CRITICAL
        assert decision.recommendation is Recommendation.BLOCK
        assert decision.score <= CFG.critical_max_score

    def test_critical_override_through_the_full_synthesis(self):
        stage1 = Stage1Result(
            initial_score=100, injection_findings=[_injection("credential_path")]
        )
        report = synthesize_verdict(
            AuditReport(skill_id="com.example.skill"), stage1, Stage2Result(), CFG
        )
        assert report.final_verdict is FinalVerdict.DANGEROUS
        assert report.trust_score <= CFG.critical_max_score
        assert report.risk is Risk.CRITICAL

    def test_reason_names_the_pattern(self):
        stage1 = Stage1Result(injection_findings=[_injection("zero_width")])
        decision = policy.decide(stage1, Stage2Result(), 100, CFG)
        assert "zero_width" in " ".join(decision.reasons)
        assert decision.critical_patterns == ["zero_width"]

    def test_critical_patterns_set_matches_the_spec(self):
        assert policy.CRITICAL_PATTERNS == frozenset(
            {
                "credential_path",
                "wallet_op",
                "exfiltration",
                "ignore_instructions",
                "hidden_block",
                "zero_width",
            }
        )

    def test_non_critical_patterns_do_not_force_critical(self):
        stage1 = Stage1Result(
            initial_score=100,
            injection_findings=[_injection("name_behaviour_mismatch", Severity.MEDIUM)],
        )
        decision = policy.decide(stage1, Stage2Result(), 100, CFG)
        assert decision.verdict is FinalVerdict.WARNING
        assert decision.risk is not Risk.CRITICAL

    def test_there_is_no_merge_path_left_to_reassert_row_1_after(self):
        """`tighten` and `enforce_critical` existed to merge a model's verdict and then
        re-assert row 1. STE-39 removed the merge, so both are gone rather than kept as code
        that suggests a model can still move the verdict."""
        assert not hasattr(policy, "tighten")
        assert not hasattr(policy, "enforce_critical")

    def test_verdict_rank_orders_strictness(self):
        ranks = [policy.verdict_rank(v) for v in (FinalVerdict.SAFE, FinalVerdict.WARNING,
                                                  FinalVerdict.DANGEROUS)]
        assert ranks == sorted(ranks) and len(set(ranks)) == 3


class TestSandboxEscape:
    def test_escape_is_dangerous_with_score_zero(self):
        decision = policy.decide(
            Stage1Result(initial_score=100), Stage2Result(escaped_sandbox=True), 100, CFG
        )
        assert decision.verdict is FinalVerdict.DANGEROUS
        assert decision.score == 0
        assert decision.risk is Risk.CRITICAL


class TestAmbiguityBias:
    def test_ambiguity_biases_to_warning(self):
        """Row 8: a grey-band score is WARNING, never SAFE."""
        stage1 = Stage1Result(initial_score=55)
        decision = policy.decide(stage1, Stage2Result(), 55, CFG)
        assert decision.verdict is FinalVerdict.WARNING
        assert decision.recommendation is Recommendation.REVIEW

    def test_the_decision_takes_no_model_input_at_all(self):
        """Row 5 (a failed model attempt forces WARNING) was removed in STE-39. The policy
        is a function of stage 1, stage 2 and the score; nothing about a model call."""
        import inspect

        assert "llm_inconclusive" not in inspect.signature(policy.decide).parameters
        stage1 = Stage1Result(initial_score=100)
        assert policy.decide(stage1, Stage2Result(), 100, CFG).verdict is FinalVerdict.SAFE

    def test_high_injection_finding_can_never_be_safe(self):
        stage1 = Stage1Result(
            initial_score=100,
            injection_findings=[_injection("undeclared_capability", Severity.HIGH)],
        )
        decision = policy.decide(stage1, Stage2Result(), 100, CFG)
        assert decision.verdict is not FinalVerdict.SAFE
        assert decision.risk is Risk.HIGH

    def test_high_injection_below_warning_threshold_is_dangerous(self):
        stage1 = Stage1Result(
            initial_score=10,
            injection_findings=[_injection("undeclared_capability", Severity.HIGH)],
        )
        decision = policy.decide(stage1, Stage2Result(), 10, CFG)
        assert decision.verdict is FinalVerdict.DANGEROUS


class TestCleanPath:
    def test_clean_and_high_score_is_safe(self):
        decision = policy.decide(Stage1Result(initial_score=100), Stage2Result(), 100, CFG)
        assert decision.verdict is FinalVerdict.SAFE
        assert decision.risk is Risk.NONE
        assert decision.recommendation is Recommendation.ALLOW

    def test_declared_risk_flags_alone_do_not_block_safe(self):
        """A skill that honestly declares NETWORK_OUTBOUND is still installable."""
        stage1 = Stage1Result(
            initial_score=75,
            risk_flags=[
                RiskFlag(
                    capability=Capability.NETWORK_OUTBOUND,
                    severity=Severity.HIGH,
                    description="declared",
                )
            ],
        )
        decision = policy.decide(stage1, Stage2Result(), 75, CFG)
        assert decision.verdict is FinalVerdict.SAFE
        assert decision.risk is Risk.LOW

    def test_low_score_with_no_findings_is_dangerous(self):
        decision = policy.decide(Stage1Result(initial_score=10), Stage2Result(), 10, CFG)
        assert decision.verdict is FinalVerdict.DANGEROUS
        assert decision.recommendation is Recommendation.BLOCK


class TestInjectionDeduction:
    def test_repeated_pattern_is_charged_once(self):
        one = [_injection("credential_path")]
        many = [_injection("credential_path") for _ in range(5)]
        assert policy.injection_deduction(one, CFG) == policy.injection_deduction(many, CFG)

    def test_distinct_patterns_accumulate(self):
        pair = [_injection("credential_path"), _injection("exfiltration")]
        assert policy.injection_deduction(pair, CFG) == 2 * CFG.injection_high_deduction

    def test_severity_rates(self):
        assert policy.injection_deduction([_injection("x", Severity.HIGH)], CFG) == 40
        assert policy.injection_deduction([_injection("y", Severity.MEDIUM)], CFG) == 15
        assert policy.injection_deduction([_injection("z", Severity.LOW)], CFG) == 5


class TestStage2Scoring:
    def test_behavioral_flags_lower_the_weighted_score(self):
        clean = synthesize_verdict(
            AuditReport(skill_id="com.example.a"), Stage1Result(initial_score=100),
            Stage2Result(), CFG,
        )
        flagged = synthesize_verdict(
            AuditReport(skill_id="com.example.b"),
            Stage1Result(initial_score=100),
            Stage2Result(
                behavioral_flags=[
                    BehavioralFlag(
                        syscall="WALLET_ACCESS",
                        expected=True,
                        severity=Severity.HIGH,
                        description="unverified",
                    )
                ]
            ),
            CFG,
        )
        assert flagged.trust_score < clean.trust_score
