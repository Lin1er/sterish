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

    def test_enforce_critical_is_idempotent(self):
        stage1 = Stage1Result(injection_findings=[_injection("wallet_op")])
        once = policy.enforce_critical(policy.decide(stage1, Stage2Result(), 100, CFG),
                                       stage1, CFG)
        twice = policy.enforce_critical(once, stage1, CFG)
        assert (once.verdict, once.score) == (twice.verdict, twice.score)

    def test_enforce_critical_reasserts_after_a_bad_merge(self):
        """Even if something upstream handed back SAFE/100, row 1 wins."""
        stage1 = Stage1Result(injection_findings=[_injection("exfiltration")])
        loose = policy.PolicyDecision(
            FinalVerdict.SAFE, Risk.NONE, Recommendation.ALLOW, 100
        )
        fixed = policy.enforce_critical(loose, stage1, CFG)
        assert fixed.verdict is FinalVerdict.DANGEROUS
        assert fixed.score <= CFG.critical_max_score
        assert "re-applied" in " ".join(fixed.reasons)


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

    def test_failed_llm_attempt_biases_to_warning(self):
        """Row 5: a score that would otherwise be SAFE becomes WARNING when the model was
        asked and could not answer."""
        stage1 = Stage1Result(initial_score=100)
        confident = policy.decide(stage1, Stage2Result(), 100, CFG)
        inconclusive = policy.decide(stage1, Stage2Result(), 100, CFG, llm_inconclusive=True)
        assert confident.verdict is FinalVerdict.SAFE
        assert inconclusive.verdict is FinalVerdict.WARNING
        assert "never to SAFE" in " ".join(inconclusive.reasons)

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


class TestTighten:
    def _base(self, verdict, risk, rec, score):
        return policy.PolicyDecision(verdict, risk, rec, score)

    def test_llm_may_raise_a_verdict(self):
        merged = policy.tighten(
            self._base(FinalVerdict.SAFE, Risk.LOW, Recommendation.ALLOW, 90),
            self._base(FinalVerdict.DANGEROUS, Risk.HIGH, Recommendation.BLOCK, 20),
        )
        assert merged.verdict is FinalVerdict.DANGEROUS
        assert merged.score == 20
        assert merged.recommendation is Recommendation.BLOCK

    def test_llm_may_not_lower_a_verdict(self):
        merged = policy.tighten(
            self._base(FinalVerdict.DANGEROUS, Risk.CRITICAL, Recommendation.BLOCK, 5),
            self._base(FinalVerdict.SAFE, Risk.NONE, Recommendation.ALLOW, 100),
        )
        assert merged.verdict is FinalVerdict.DANGEROUS
        assert merged.risk is Risk.CRITICAL
        assert merged.recommendation is Recommendation.BLOCK
        assert merged.score == 5

    def test_score_is_the_minimum(self):
        merged = policy.tighten(
            self._base(FinalVerdict.WARNING, Risk.MEDIUM, Recommendation.REVIEW, 60),
            self._base(FinalVerdict.WARNING, Risk.MEDIUM, Recommendation.REVIEW, 42),
        )
        assert merged.score == 42

    def test_reasons_are_concatenated(self):
        a = policy.PolicyDecision(FinalVerdict.SAFE, Risk.NONE, Recommendation.ALLOW, 100, ["a"])
        b = policy.PolicyDecision(FinalVerdict.SAFE, Risk.NONE, Recommendation.ALLOW, 100, ["b"])
        assert policy.tighten(a, b).reasons == ["a", "b"]


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
