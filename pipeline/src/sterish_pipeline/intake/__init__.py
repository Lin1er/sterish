"""Skill intake: fetch, normalize, hash, and store auditable skills."""

from sterish_pipeline.intake.corpus import (
    Corpus,
    CorpusEntry,
    CorpusError,
    Provenance,
)
from sterish_pipeline.intake.injection import (
    InjectionCategory,
    InjectionFinding,
    InjectionScanResult,
    InjectionSeverity,
    dedupe_findings,
    scan_manifest,
    scan_text,
)
from sterish_pipeline.intake.normalize import (
    NormalizationError,
    NormalizedSkill,
    SourceKind,
    detect_kind,
    normalize,
    parse_frontmatter,
)

__all__ = [
    "Corpus",
    "CorpusEntry",
    "CorpusError",
    "InjectionCategory",
    "InjectionFinding",
    "InjectionScanResult",
    "InjectionSeverity",
    "NormalizationError",
    "NormalizedSkill",
    "Provenance",
    "SourceKind",
    "dedupe_findings",
    "detect_kind",
    "normalize",
    "parse_frontmatter",
    "scan_manifest",
    "scan_text",
]
