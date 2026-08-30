from sterish_pipeline.models import Capability, Severity, SkillManifest, Stage2Result, BehavioralFlag, ToolDef
from sterish_pipeline.stages.stage2_sandbox_check import run_sandbox_check, _static_fallback


def _make_manifest(caps: list[Capability]) -> SkillManifest:
    return SkillManifest(
        skill_id="test.sandbox",
        name="Sandbox Test",
        description="Test",
        version="1.0.0",
        permissions=[],
        tools=[ToolDef(name="t", description="", input_schema={}, capabilities=caps)],
    )


class TestStage2:
    def test_static_fallback_flags_high_caps(self):
        caps = {Capability.WALLET_ACCESS, Capability.SECRET_READ}
        flags = _static_fallback(caps)
        assert len(flags) == 2
        assert all(f.severity == Severity.HIGH for f in flags)

    def test_static_fallback_flags_medium_caps(self):
        caps = {Capability.FILE_WRITE, Capability.ENV_READ}
        flags = _static_fallback(caps)
        assert all(f.severity == Severity.MEDIUM for f in flags)

    def test_static_fallback_empty(self):
        flags = _static_fallback(set())
        assert len(flags) == 0

    def test_run_sandbox_check_returns_result(self):
        manifest = _make_manifest([Capability.FILE_READ])
        result = run_sandbox_check(manifest)
        assert isinstance(result, Stage2Result)
        assert isinstance(result.behavioral_flags, list)

    def test_run_sandbox_check_no_docker(self):
        manifest = _make_manifest([Capability.WALLET_ACCESS, Capability.NETWORK_OUTBOUND])
        result = run_sandbox_check(manifest)
        assert result.escaped_sandbox is False
        # Should fall back to static analysis.
        high_flags = [f for f in result.behavioral_flags if f.severity == Severity.HIGH]
        assert len(high_flags) == 2
