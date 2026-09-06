"""Register the committed fixtures into the corpus index.

The catalog snapshots come from `intake fetch`; the poisoned and safe fixtures
are authored in-repo (they are the attack/clean baseline the seed run needs).
This script hashes them and merges them into the existing index without
disturbing the fetched catalog entries.

Run from the pipeline directory:

    uv run python scripts/build_fixture_corpus.py
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sterish_pipeline.content_hash import read_skill_files
from sterish_pipeline.intake.corpus import Corpus, Provenance
from sterish_pipeline.intake.normalize import SourceKind

CORPUS_DIR = Path("corpus")
FIXTURE_ROOT = "fixtures"

# (dir, skill_id, version, kind, label, expected_verdict, note)
FIXTURES = [
    (
        "poisoned-pdf-skill",
        "com.fixtures.poisoned.pdf-summarizer",
        "1.4.0",
        SourceKind.AGENT_SKILL,
        "poisoned",
        "DANGEROUS",
        "ethnyc-style: benign frontmatter, credential-exfil instructions in the body.",
    ),
    (
        "hidden-comment-skill",
        "com.fixtures.poisoned.markdown-linter",
        "2.0.1",
        SourceKind.AGENT_SKILL,
        "poisoned",
        "DANGEROUS",
        "Payload hidden in an HTML comment invisible to a human reader.",
    ),
    (
        "evil-mcp",
        "com.fixtures.poisoned.invoice-helper",
        "1.0.0",
        SourceKind.MCP_SERVER,
        "poisoned",
        "DANGEROUS",
        "MCP server: autoApprove:['*'], tool shadowing, wallet drain in env.",
    ),
    (
        "token-drainer-mcp",
        "com.fixtures.poisoned.token-drainer",
        "1.0.0",
        SourceKind.MCP_SERVER,
        "poisoned",
        "DANGEROUS",
        "Ported from the scaffold poisoned fixture; declared wallet+secret drain.",
    ),
    (
        "safe-weather-skill",
        "com.fixtures.safe.weather-lookup",
        "1.2.0",
        SourceKind.AGENT_SKILL,
        "safe",
        "SAFE",
        "Legitimate read-only network skill.",
    ),
    (
        "price-checker",
        "com.fixtures.safe.price-checker",
        "0.9.0",
        SourceKind.AGENT_SKILL,
        "safe",
        "SAFE",
        "Legitimate read-only network skill.",
    ),
    (
        "premium-pdf-suite",
        "com.fixtures.safe.premium-pdf-suite",
        "3.1.0",
        SourceKind.AGENT_SKILL,
        "safe",
        "SAFE",
        "Legitimate local PDF tool; read+write of named files stays SAFE by default.",
    ),
]


def main() -> None:
    corpus = Corpus(CORPUS_DIR)
    entries = {e.skill_id: e for e in corpus.load()} if corpus.index_path.exists() else {}

    for folder, skill_id, version, kind, label, expected, note in FIXTURES:
        source_dir = corpus.root / FIXTURE_ROOT / folder
        files = read_skill_files(source_dir)
        entry = corpus.write_entry(
            skill_id=skill_id,
            version=version,
            kind=kind,
            files=files,
            relative_path=f"{FIXTURE_ROOT}/{folder}",
            provenance=Provenance(
                source="sterish-fixture",
                source_url=f"repo:pipeline/corpus/{FIXTURE_ROOT}/{folder}",
                fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
                note=note,
            ),
            label=label,
            expected_verdict=expected,
        )
        entries[entry.skill_id] = entry
        print(f"  {label:8} {skill_id}  {entry.content_hash[:12]}  -> expect {expected}")

    corpus.save_index(list(entries.values()), datetime.now(UTC).isoformat(timespec="seconds"))
    print(f"Index now holds {len(entries)} entries at {corpus.index_path}")


if __name__ == "__main__":
    main()
