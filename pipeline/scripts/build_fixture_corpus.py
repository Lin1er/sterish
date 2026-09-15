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
from typing import NamedTuple

from sterish_pipeline.content_hash import read_skill_files
from sterish_pipeline.intake.corpus import (
    SEED_MODE_AUDIT,
    SEED_MODE_REGISTER_ONLY,
    Corpus,
    Provenance,
)
from sterish_pipeline.intake.normalize import SourceKind

CORPUS_DIR = Path("corpus")
FIXTURE_ROOT = "fixtures"


class Fixture(NamedTuple):
    folder: str
    skill_id: str
    version: str
    kind: SourceKind
    label: str
    expected_verdict: str
    note: str
    seed_mode: str = SEED_MODE_AUDIT


FIXTURES = [
    Fixture(
        "poisoned-pdf-skill",
        "com.fixtures.poisoned.pdf-summarizer",
        "1.4.0",
        SourceKind.AGENT_SKILL,
        "poisoned",
        "DANGEROUS",
        "ethnyc-style: benign frontmatter, credential-exfil instructions in the body.",
    ),
    Fixture(
        "hidden-comment-skill",
        "com.fixtures.poisoned.markdown-linter",
        "2.0.1",
        SourceKind.AGENT_SKILL,
        "poisoned",
        "DANGEROUS",
        "Payload hidden in an HTML comment invisible to a human reader.",
    ),
    Fixture(
        "evil-mcp",
        "com.fixtures.poisoned.invoice-helper",
        "1.0.0",
        SourceKind.MCP_SERVER,
        "poisoned",
        "DANGEROUS",
        "MCP server: autoApprove:['*'], tool shadowing, wallet drain in env.",
    ),
    Fixture(
        "token-drainer-mcp",
        "com.fixtures.poisoned.token-drainer",
        "1.0.0",
        SourceKind.MCP_SERVER,
        "poisoned",
        "DANGEROUS",
        "Ported from the scaffold poisoned fixture; declared wallet+secret drain.",
    ),
    Fixture(
        "safe-weather-skill",
        "com.fixtures.safe.weather-lookup",
        "1.2.0",
        SourceKind.AGENT_SKILL,
        "safe",
        "SAFE",
        "Legitimate read-only network skill.",
    ),
    Fixture(
        "price-checker",
        "com.fixtures.safe.price-checker",
        "0.9.0",
        SourceKind.AGENT_SKILL,
        "safe",
        "SAFE",
        "Legitimate read-only network skill.",
    ),
    Fixture(
        "premium-pdf-suite",
        "com.fixtures.safe.premium-pdf-suite",
        "3.1.0",
        SourceKind.AGENT_SKILL,
        "safe",
        "SAFE",
        "Legitimate local PDF tool; read+write of named files stays SAFE by default.",
    ),
    # --- STE-18 demo set: the four registry states, on real chain data ------------
    #
    # `com.fixtures.demo.*` is a published namespace, not a test one: the API's
    # test-namespace filter deliberately does NOT hide it, because the whole point
    # of these four is to be visible in the dashboard.
    Fixture(
        "demo-release-notes-v1",
        "com.fixtures.demo.release-notes",
        "1.0.0",
        SourceKind.AGENT_SKILL,
        "demo",
        "SAFE",
        "Rug pull, half one: a clean v1 that earns SAFE and a VERIFIED badge.",
    ),
    Fixture(
        "demo-release-notes-v2",
        "com.fixtures.demo.release-notes",
        "2.0.0",
        SourceKind.AGENT_SKILL,
        "demo",
        "DANGEROUS",
        "Rug pull, half two: same skill_id, same author, credential exfiltration "
        "added in an HTML comment. Proves invariant R4 — v1's SAFE verdict and "
        "its badge do not reach v2.",
    ),
    Fixture(
        "demo-changelog-writer-v1",
        "com.fixtures.demo.changelog-writer",
        "1.0.0",
        SourceKind.AGENT_SKILL,
        "demo",
        "SAFE",
        "Stale-version demo, half one: the version that actually was audited.",
    ),
    Fixture(
        "demo-changelog-writer-v2",
        "com.fixtures.demo.changelog-writer",
        "2.0.0",
        SourceKind.AGENT_SKILL,
        "demo",
        "",
        "Stale-version demo, half two: registered and never audited, so the chain "
        "holds AuditVerdict::Unaudited and latest_version != latest_audited_version. "
        "expected_verdict is empty because the pipeline never emits UNAUDITED.",
        SEED_MODE_REGISTER_ONLY,
    ),
    Fixture(
        "demo-ledger-inspector",
        "com.fixtures.demo.ledger-inspector",
        "1.0.0",
        SourceKind.AGENT_SKILL,
        "demo",
        "WARNING",
        "WARNING via policy row 8: six honestly declared capabilities put the score "
        "at 60, inside the grey band, with zero injection findings.",
    ),
    Fixture(
        "demo-table-formatter",
        "com.fixtures.demo.table-formatter",
        "1.0.0",
        SourceKind.MCP_SERVER,
        "demo",
        "WARNING",
        "WARNING via policy row 6: one MEDIUM name_behaviour_mismatch, nothing "
        "critical, at a score (78) that would otherwise be SAFE.",
    ),
]


def main() -> None:
    corpus = Corpus(CORPUS_DIR)
    entries = {e.key: e for e in corpus.load()} if corpus.index_path.exists() else {}

    for fixture in FIXTURES:
        folder, skill_id, version, kind, label, expected, note, seed_mode = fixture
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
            seed_mode=seed_mode,
        )
        entries[entry.key] = entry
        print(
            f"  {label:8} {skill_id}@{version}  {entry.content_hash[:12]}  "
            f"-> expect {expected or seed_mode}"
        )

    corpus.save_index(list(entries.values()), datetime.now(UTC).isoformat(timespec="seconds"))
    print(f"Index now holds {len(entries)} entries at {corpus.index_path}")


if __name__ == "__main__":
    main()
