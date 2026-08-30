from sterish_pipeline.models import (
    AuditReport, FinalVerdict, Severity, Stage1Result, Stage2Result, RiskFlag, Capability
)
from sterish_pipeline.stages.stage3_verdict_synthesis import synthesize_verdict
from sterish_pipeline.config import PipelineConfig


class TestStage3:
    def test_safe_verdict(self):
        report = AuditReport(skill_id="test.safe")
        stage1 = Stage1Result(initial_score=90, reasoning="Low risk")
        stage2 = Stage2Result()
        cfg = PipelineConfig(safe_threshold=70, warning_threshold=40, stage1_weight=50, stage2_weight=50)
        result = synthesize_verdict(report, stage1, stage2, cfg)
        assert result.final_verdict == FinalVerdict.SAFE
        assert result.trust_score >= 70
        assert result.evidence_hash != ""

    def test_dangerous_verdict_low_score(self):
        report = AuditReport(skill_id="test.danger")
        stage1 = Stage1Result(initial_score=10, reasoning="Many risks")
        stage2 = Stage2Result()
        cfg = PipelineConfig(safe_threshold=70, warning_threshold=40, stage1_weight=50, stage2_weight=50)
        result = synthesize_verdict(report, stage1, stage2, cfg)
        # score = 10*50 + 100*50 = 5500 // 100 = 55 >= 40 = WARNING, not DANGEROUS
        # Need score < 40: use stage1_weight=100
        cfg2 = PipelineConfig(safe_threshold=70, warning_threshold=40, stage1_weight=100, stage2_weight=0)
        result = synthesize_verdict(report, stage1, stage2, cfg2)
        assert result.final_verdict == FinalVerdict.DANGEROUS

    def test_warning_verdict(self):
        report = AuditReport(skill_id="test.warn")
        stage1 = Stage1Result(initial_score=55, reasoning="Some risk")
        stage2 = Stage2Result()
        # score = 55*100 + 100*0 = 5500 // 100 = 55 -> WARNING (>=40, <70)
        cfg = PipelineConfig(safe_threshold=70, warning_threshold=40, stage1_weight=100, stage2_weight=0)
        result = synthesize_verdict(report, stage1, stage2, cfg)
        assert result.final_verdict == FinalVerdict.WARNING

    def test_sandbox_escape_is_dangerous(self):
        report = AuditReport(skill_id="test.escaped")
        stage1 = Stage1Result(initial_score=100, reasoning="Clean")
        stage2 = Stage2Result(escaped_sandbox=True)
        cfg = PipelineConfig(safe_threshold=70, warning_threshold=40)
        result = synthesize_verdict(report, stage1, stage2, cfg)
        assert result.final_verdict == FinalVerdict.DANGEROUS
        assert result.trust_score == 0

    def test_evidence_hash_deterministic(self):
        report = AuditReport(skill_id="test.hash")
        stage1 = Stage1Result(initial_score=80, reasoning="test")
        stage2 = Stage2Result()
        cfg = PipelineConfig()
        r1 = synthesize_verdict(report, stage1, stage2, cfg)
        r2 = synthesize_verdict(AuditReport(skill_id="test.hash"), stage1, stage2, cfg)
        assert r1.evidence_hash == r2.evidence_hash

    def test_recommendation_populated(self):
        report = AuditReport(skill_id="test.rec")
        stage1 = Stage1Result(initial_score=90, reasoning="Clean")
        stage2 = Stage2Result()
        cfg = PipelineConfig()
        result = synthesize_verdict(report, stage1, stage2, cfg)
        assert "trust score" in result.recommendation.lower()
