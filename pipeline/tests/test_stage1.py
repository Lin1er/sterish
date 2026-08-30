import json
from pathlib import Path

from sterish_pipeline.models import Capability, Severity, SkillManifest, ToolDef
from sterish_pipeline.stages.stage1_desc_scanner import scan_description
from sterish_pipeline.config import PipelineConfig


def _make_manifest(caps: list[Capability]) -> SkillManifest:
    return SkillManifest(
        skill_id="test.skill",
        name="Test Skill",
        description="A test skill",
        version="1.0.0",
        permissions=[],
        tools=[ToolDef(
            name="tool1",
            description="A tool",
            input_schema={},
            capabilities=caps,
        )],
    )


class TestStage1:
    def test_safe_skill_scores_100(self):
        manifest = _make_manifest([Capability.FILE_READ])
        result = scan_description(manifest)
        assert result.initial_score == 97  # 100 - 3 (LOW)
        assert len(result.risk_flags) == 1
        assert result.risk_flags[0].capability == Capability.FILE_READ
        assert result.risk_flags[0].severity == Severity.LOW

    def test_high_risk_caps_deduct_25_each(self):
        manifest = _make_manifest([Capability.WALLET_ACCESS, Capability.SECRET_READ])
        result = scan_description(manifest)
        # 100 - 25 - 25 = 50
        assert result.initial_score == 50
        high_flags = [f for f in result.risk_flags if f.severity == Severity.HIGH]
        assert len(high_flags) == 2

    def test_mixed_caps(self):
        manifest = _make_manifest([
            Capability.WALLET_ACCESS,
            Capability.FILE_WRITE,
            Capability.FILE_READ,
        ])
        result = scan_description(manifest)
        # 100 - 25 - 10 - 3 = 62
        assert result.initial_score == 62

    def test_no_tools_no_flags(self):
        manifest = SkillManifest(
            skill_id="test.empty",
            name="Empty Skill",
            description="No tools",
            version="1.0.0",
            permissions=[],
            tools=[],
        )
        result = scan_description(manifest)
        assert result.initial_score == 100
        assert len(result.risk_flags) == 0
        assert "No risk flags" in result.reasoning

    def test_custom_config(self):
        cfg = PipelineConfig(high_risk_deduction=50)
        manifest = _make_manifest([Capability.NETWORK_OUTBOUND])
        result = scan_description(manifest, config=cfg)
        assert result.initial_score == 50

    def test_deduplication(self):
        manifest = SkillManifest(
            skill_id="test.dup",
            name="Dup Skill",
            description="Test",
            version="1.0.0",
            permissions=[],
            tools=[
                ToolDef(name="a", description="", input_schema={}, capabilities=[Capability.WALLET_ACCESS]),
                ToolDef(name="b", description="", input_schema={}, capabilities=[Capability.WALLET_ACCESS]),
            ],
        )
        result = scan_description(manifest)
        wallet_flags = [f for f in result.risk_flags if f.capability == Capability.WALLET_ACCESS]
        assert len(wallet_flags) == 1

    def test_poisoned_skill_manifest(self):
        path = Path(__file__).parent / "poisoned_skill" / "manifest.json"
        data = json.loads(path.read_text())
        manifest = SkillManifest.model_validate(data)
        result = scan_description(manifest)
        assert result.initial_score < 30
        high_caps = {f.capability for f in result.risk_flags if f.severity == Severity.HIGH}
        assert Capability.WALLET_ACCESS in high_caps
        assert Capability.SECRET_READ in high_caps
