"""End-to-end audit: manifest in, frozen verdict document out.

    run_audit("pipeline/tests/fixtures/poisoned_pdf_skill")
        -> AuditRun(report=..., document=VerdictDocument(...), content_hash="...")

The order is fixed and each step is a pure function of the one before it:

    stage 1  run_stage1            declared capabilities + description-injection scan
    stage 2  run_sandbox_check     declared-vs-actual static analysis (Docker optional)
    stage 3  synthesize_verdict    weighted score, then the policy decision table
             synthesize_with_llm   optional advisory second opinion (fail-soft)
             policy.tighten        merge -- the model may only tighten
             policy.enforce_critical  re-assert the critical override
             build_verdict_document   assemble the frozen v1 document

``content_hash`` comes from the frozen reference implementation via ``specs.hash_dir``; the
whole run is deterministic when no model is involved, which is what makes the fixtures
testable as regressions rather than as vibes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sterish_pipeline import specs
from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.llm import (
    LLMOpinion,
    StructuredClient,
    api_key_present,
    synthesize_with_llm,
)
from sterish_pipeline.models import (
    AuditReport,
    SkillManifest,
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
    """Whether stage 3 is going to ask a model at all.

    The distinction drives policy row 5: *asking and failing* is inconclusive evidence and
    biases the verdict to WARNING, while *not asking* (no key configured) is a deterministic
    mode that leaves the verdict alone.
    """
    if not config.use_llm:
        return False
    return client is not None or api_key_present()


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
    stage2 = Stage2Result() if skip_sandbox else run_sandbox_check(manifest, config=cfg)

    report = AuditReport(skill_id=manifest.skill_id, version=manifest.version)
    report = synthesize_verdict(report, stage1, stage2, cfg)

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

    if attempted and opinion is None:
        # Row 5: asked, no usable answer -> ambiguity biases to WARNING, never to SAFE.
        report = synthesize_verdict(report, stage1, stage2, cfg, llm_inconclusive=True)
    elif opinion is not None:
        baseline = policy.PolicyDecision(
            verdict=report.final_verdict,
            risk=report.risk,
            recommendation=report.recommendation_code,
            score=report.trust_score,
            reasons=list(report.policy_reasons),
            critical_patterns=sorted(
                {f.pattern_id for f in policy.critical_findings(stage1.injection_findings)}
            ),
        )
        advisory = policy.PolicyDecision(
            verdict=opinion.verdict,
            risk=opinion.risk,
            recommendation=opinion.recommendation,
            score=opinion.score,
            reasons=[
                f"{policy.LLM_REASON_PREFIX}{opinion.model}): {opinion.rationale}"
            ],
        )
        merged = policy.enforce_critical(policy.tighten(baseline, advisory), stage1, cfg)
        report.final_verdict = merged.verdict
        report.risk = merged.risk
        report.recommendation_code = merged.recommendation
        report.trust_score = merged.score
        report.policy_reasons = merged.reasons

    report.llm_attempted = attempted
    report.llm_used = opinion is not None
    report.llm_model = cfg.llm_model if opinion is not None else ""
    report.llm_notes = notes

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
