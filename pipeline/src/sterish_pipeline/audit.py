"""Run the full audit over a normalized skill and produce an AuditReport.

The CLI's `audit` command and the corpus batch both go through here, so the
verdict a single skill gets is exactly the verdict it gets in a batch run.
"""

from __future__ import annotations

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.content_hash import content_hash
from sterish_pipeline.intake.normalize import NormalizedSkill
from sterish_pipeline.models import AuditReport, SkillManifest, Stage2Result
from sterish_pipeline.stages import run_sandbox_check, scan_description, synthesize_verdict


def audit_manifest(
    manifest: SkillManifest,
    config: PipelineConfig | None = None,
    skip_sandbox: bool = False,
    extra_text: dict[str, str] | None = None,
    content_hash_value: str = "",
) -> AuditReport:
    """Audit a manifest and return the completed report."""
    cfg = config or PipelineConfig()
    report = AuditReport(
        skill_id=manifest.skill_id,
        version=manifest.version,
        content_hash=content_hash_value,
    )

    stage1 = scan_description(manifest, cfg, extra_text=extra_text)
    stage2 = Stage2Result() if skip_sandbox else run_sandbox_check(manifest, config=cfg)
    return synthesize_verdict(report, stage1, stage2, cfg)


def audit_normalized(
    skill: NormalizedSkill,
    config: PipelineConfig | None = None,
    skip_sandbox: bool = False,
) -> AuditReport:
    """Audit a normalized skill, hashing its snapshot bytes for the report.

    The markdown bodies and MCP env blocks the normalizer set aside are folded
    into the stage-1 injection scan — that is where a poisoned skill hides its
    payload.
    """
    digest = content_hash(skill.files)
    return audit_manifest(
        skill.manifest,
        config=config,
        skip_sandbox=skip_sandbox,
        extra_text=skill.extra_text,
        content_hash_value=digest,
    )
