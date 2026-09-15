"""End-to-end audit: manifest in, frozen verdict document out.

    run_audit("pipeline/tests/fixtures/poisoned_pdf_skill")
        -> AuditRun(report=..., document=VerdictDocument(...), content_hash="...")

The order is fixed and each step is a pure function of the one before it:

    stage 1  run_stage1            declared capabilities + description-injection scan
    stage 2  run_sandbox_check     runs the entrypoint under strace; not applicable when
                                   the skill has none (STE-40)
    stage 3  synthesize_verdict    weighted score, then the policy decision table
             synthesize_with_llm   optional second opinion, recorded as llm_advisory only
                                   (STE-39: it never moves the verdict)
             build_verdict_document   assemble the frozen v1 document

``content_hash`` comes from the frozen reference implementation via ``specs.hash_dir``; the
whole run is deterministic when no model is involved, which is what makes the fixtures
testable as regressions rather than as vibes.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from sterish_pipeline import specs
from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.content_hash import content_hash, read_skill_files
from sterish_pipeline.llm import (
    LLMOpinion,
    StructuredClient,
    api_key_present,
    synthesize_with_llm,
)
from sterish_pipeline.models import (
    AuditReport,
    LLMAdvisory,
    SkillManifest,
    Stage1Result,
    Stage2Result,
    VerdictDocument,
    to_verdict_json,
)
from sterish_pipeline.stages import policy
from sterish_pipeline.stages.stage1_desc_scanner import run_stage1
from sterish_pipeline.stages.stage2_sandbox_check import run_sandbox_check
from sterish_pipeline.stages.stage3_verdict_synthesis import (
    build_verdict_document,
    synthesize_verdict,
)

if TYPE_CHECKING:  # avoids a cycle: intake.normalize imports this module
    from sterish_pipeline.intake.normalize import NormalizedSkill

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"


@dataclass
class AuditRun:
    """Everything one audit produced."""

    manifest: SkillManifest
    skill_dir: Path
    content_hash: str
    report: AuditReport
    document: VerdictDocument
    llm_opinion: LLMOpinion | None = None
    notes: list[str] = field(default_factory=list)

    def verdict_json(self) -> dict:
        """The document in the exact JSON shape the frozen schema accepts."""
        return to_verdict_json(self.document)

    def validate(self, submittable: bool = False) -> None:
        """Raise ``ValueError`` unless the emitted document satisfies the frozen schema."""
        specs.validate_verdict_document(self.verdict_json(), submittable=submittable)


def audit_normalized(
    skill: NormalizedSkill,
    config: PipelineConfig | None = None,
    skip_sandbox: bool = False,
    llm_client: StructuredClient | None = None,
) -> AuditReport:
    """Audit a skill that was normalised from a non-manifest source.

    Corpus entries are SKILL.md files and MCP JSON, not ``manifest.json``, so
    ``run_audit`` cannot read them directly — the intake normaliser produces the
    manifest first.

    The normalised bytes are materialised into a temporary directory and stage 1
    is pointed at it, so the injection scanner reads exactly the bytes the
    content_hash was taken over. That also means the markdown bodies and MCP env
    blocks are covered by STE-14's scanner rather than by a second text-collection
    path of this module's own.
    """
    cfg = config or PipelineConfig()

    with tempfile.TemporaryDirectory(prefix="sterish-normalized-") as tmp:
        root = Path(tmp)
        for rel, raw in skill.files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)

        stage1 = run_stage1(skill.manifest, cfg, root)

    stage2 = (
        Stage2Result()
        if skip_sandbox
        else run_sandbox_check(skill.manifest, config=cfg, files=skill.files)
    )

    report = AuditReport(skill_id=skill.manifest.skill_id, version=skill.manifest.version)
    report.content_hash = content_hash(skill.files)
    report = synthesize_verdict(report, stage1, stage2, cfg)
    report, _ = apply_llm(report, skill.manifest, stage1, stage2, cfg, llm_client)
    return report


def load_skill(path: Path | str) -> tuple[SkillManifest, Path]:
    """Accept either a skill directory or the path to its ``manifest.json``.

    The directory matters beyond convenience: ``content_hash`` is computed over the whole
    directory, and ``SKILL.md`` is part of the text the scanner reads.
    """
    p = Path(path)
    if p.is_dir():
        skill_dir, manifest_path = p, p / MANIFEST_NAME
    else:
        skill_dir, manifest_path = p.parent, p
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no {MANIFEST_NAME} at {manifest_path}")
    manifest = SkillManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    return manifest, skill_dir


def _llm_will_be_attempted(config: PipelineConfig, client: StructuredClient | None) -> bool:
    """Whether stage 3 is going to ask a model at all. Recorded, never acted on."""
    if not config.use_llm:
        return False
    return client is not None or api_key_present()


def apply_llm(
    report: AuditReport,
    manifest: SkillManifest,
    stage1: Stage1Result,
    stage2: Stage2Result,
    cfg: PipelineConfig,
    llm_client: StructuredClient | None,
) -> tuple[AuditReport, LLMOpinion | None]:
    """Ask the model for a second opinion and record it beside the verdict (STE-39).

    Shared by `run_audit` and `audit_normalized`. Until STE-39 the opinion was merged with
    `policy.tighten` — the model could raise the verdict and lower the score — and a model
    that was asked but failed forced WARNING. Both are gone. The same skill, same bytes and
    same config returned three different model answers in five runs, so a model-moved
    verdict could not be reproduced by the third party `docs/audit-evidence.md` invites to
    re-run the audit, and a gateway outage would have changed a verdict about bytes that
    had not changed.

    What stays: the model is still asked, its answer is still validated, and it is recorded
    as `report.llm_advisory` with whether it is stricter than or disagrees with the verdict.
    None of that, nor the notes, reaches the verdict document or `evidence_hash`.
    """
    attempted = _llm_will_be_attempted(cfg, llm_client)
    opinion: LLMOpinion | None = None
    notes: list[str] = []

    if cfg.use_llm:
        opinion, notes = synthesize_with_llm(
            manifest,
            stage1,
            stage2,
            baseline_verdict=report.final_verdict.value,
            baseline_risk=report.risk.value,
            baseline_score=report.trust_score,
            baseline_recommendation=report.recommendation_code.value,
            config=cfg,
            client=llm_client,
        )

    report.llm_advisory = None
    if opinion is not None:
        rank = policy.verdict_rank
        report.llm_advisory = LLMAdvisory(
            verdict=opinion.verdict,
            risk=opinion.risk,
            score=opinion.score,
            recommendation=opinion.recommendation,
            rationale=opinion.rationale,
            model=opinion.model,
            stricter_than_verdict=rank(opinion.verdict) > rank(report.final_verdict),
            disagrees_with_verdict=opinion.verdict is not report.final_verdict,
        )

    report.llm_attempted = attempted
    report.llm_used = opinion is not None
    report.llm_model = cfg.llm_model if opinion is not None else ""
    report.llm_notes = notes
    return report, opinion


def run_audit(
    path: Path | str,
    config: PipelineConfig | None = None,
    skip_sandbox: bool = False,
    llm_client: StructuredClient | None = None,
) -> AuditRun:
    """Run all three stages over a skill directory and emit a frozen verdict document."""
    cfg = config or PipelineConfig()
    manifest, skill_dir = load_skill(path)
    content_hash = specs.hash_dir(skill_dir)

    stage1 = run_stage1(manifest, cfg, skill_dir)
    stage2 = (
        Stage2Result()
        if skip_sandbox
        else run_sandbox_check(manifest, config=cfg, files=read_skill_files(skill_dir))
    )

    report = AuditReport(skill_id=manifest.skill_id, version=manifest.version)
    report = synthesize_verdict(report, stage1, stage2, cfg)
    # One implementation of the model step for both entry points. This was a second copy,
    # which is how the two drifted apart once before (STE-38).
    report, opinion = apply_llm(report, manifest, stage1, stage2, cfg, llm_client)
    notes = report.llm_notes

    document = build_verdict_document(report, manifest, content_hash, cfg)

    return AuditRun(
        manifest=manifest,
        skill_dir=skill_dir,
        content_hash=content_hash,
        report=report,
        document=document,
        llm_opinion=opinion,
        notes=notes,
    )
