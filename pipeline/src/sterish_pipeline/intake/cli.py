"""`sterish-pipeline intake ...` and the corpus batch audit.

Three commands make up the intake surface:

* ``intake fetch``  — pull the Stellar catalog into corpus snapshots (network).
* ``intake verify`` — recompute every hash from the snapshot bytes (offline).
* ``audit-corpus``  — audit every corpus entry in one run (offline, no key).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from sterish_pipeline.audit import audit_normalized
from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.content_hash import content_hash, hash_bytes
from sterish_pipeline.intake.corpus import Corpus, CorpusEntry, Provenance
from sterish_pipeline.intake.normalize import SourceKind
from sterish_pipeline.models import FinalVerdict

console = Console(legacy_windows=False, safe_box=True)

DEFAULT_CORPUS = Path("corpus")


@click.group()
def intake() -> None:
    """Fetch, verify, and manage the audit corpus."""


@intake.command("fetch")
@click.option("--corpus", "corpus_dir", default=str(DEFAULT_CORPUS), type=click.Path())
@click.option("--limit", type=int, default=None, help="Cap the number of catalog docs")
@click.option("--timeout", type=float, default=30.0)
def fetch(corpus_dir: str, limit: int | None, timeout: float) -> None:
    """Snapshot skills.stellar.org into the corpus (the only networked command)."""
    from sterish_pipeline.intake.sources import fetch_catalog

    corpus = Corpus(corpus_dir)
    existing = _load_existing(corpus)

    console.print("[bold]Fetching Stellar skills catalog...[/bold]")
    documents = fetch_catalog(timeout=timeout, limit=limit)
    console.print(f"  discovered {len(documents)} catalog document(s)")

    for doc in documents:
        files = {doc.filename: doc.body}
        entry = corpus.write_entry(
            skill_id=doc.skill_id,
            version=doc.version,
            kind=SourceKind.AGENT_SKILL,
            files=files,
            relative_path=f"catalog/{doc.slug}",
            provenance=Provenance(
                source="skills.stellar.org",
                source_url=doc.url,
                fetched_at=doc.fetched_at,
                upstream_etag=doc.etag,
                upstream_last_modified=doc.last_modified,
            ),
            label="catalog",
            expected_verdict="",
        )
        existing[entry.skill_id] = entry
        console.print(f"  [green]+[/green] {entry.skill_id} ({entry.content_hash[:12]}…)")

    corpus.save_index(list(existing.values()), datetime.now(UTC).isoformat(timespec="seconds"))
    console.print(f"[bold green]Wrote {len(existing)} entries[/bold green] to {corpus.index_path}")


@intake.command("verify")
@click.option("--corpus", "corpus_dir", default=str(DEFAULT_CORPUS), type=click.Path())
def verify(corpus_dir: str) -> None:
    """Recompute every hash from the snapshot bytes; nonzero exit on any drift."""
    corpus = Corpus(corpus_dir)
    problems = corpus.verify_all()
    entries = corpus.load()
    if problems:
        console.print(f"[bold red]{len(problems)} integrity problem(s):[/bold red]")
        for problem in problems:
            console.print(f"  [red]x[/red] {problem}")
        raise SystemExit(1)
    console.print(f"[bold green]OK[/bold green] — {len(entries)} entries, all hashes match bytes")


@intake.command("rehash")
@click.option("--corpus", "corpus_dir", default=str(DEFAULT_CORPUS), type=click.Path())
def rehash(corpus_dir: str) -> None:
    """Recompute content_hash/file_digests from disk and rewrite the index.

    For use only after a deliberate spec change (see docs/specs/content-hash.md).
    """
    corpus = Corpus(corpus_dir)
    entries = corpus.load()
    for entry in entries:
        files = corpus.read_files(entry)
        entry.content_hash = content_hash(files)
        entry.file_digests = {p: hash_bytes(b) for p, b in sorted(files.items())}
    corpus.save_index(entries, datetime.now(UTC).isoformat(timespec="seconds"))
    console.print(f"[green]Rehashed {len(entries)} entries[/green]")


@click.command("audit-corpus")
@click.option("--corpus", "corpus_dir", default=str(DEFAULT_CORPUS), type=click.Path())
@click.option("--config", "-c", default=None, help="Pipeline config JSON")
@click.option("--skip-sandbox", is_flag=True, default=True, help="Skip stage 2 (default on)")
@click.option("--json-out", type=click.Path(), default=None, help="Write full reports as JSON")
@click.option("--strict", is_flag=True, help="Exit nonzero if any expected verdict is missed")
def audit_corpus(
    corpus_dir: str,
    config: str | None,
    skip_sandbox: bool,
    json_out: str | None,
    strict: bool,
) -> None:
    """Audit every corpus entry in one deterministic, offline run."""
    cfg = PipelineConfig.load(config)
    corpus = Corpus(corpus_dir)
    entries = corpus.load()
    if not entries:
        console.print("[red]corpus is empty[/red]")
        raise SystemExit(1)

    table = Table("skill_id", "kind", "verdict", "score", "expected", "inj", "result")
    reports: list[dict] = []
    mismatches: list[str] = []
    poisoned_marked_safe: list[str] = []

    for entry in sorted(entries, key=lambda e: e.skill_id):
        skill = corpus.normalized(entry)
        report = audit_normalized(skill, config=cfg, skip_sandbox=skip_sandbox)

        verdict = report.final_verdict.value
        injection = len(report.stage1.injection_flags)
        result = "—"
        if entry.expected_verdict:
            ok = verdict == entry.expected_verdict
            result = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
            if not ok:
                mismatches.append(
                    f"{entry.skill_id}: expected {entry.expected_verdict}, got {verdict}"
                )
        if entry.is_poisoned and report.final_verdict == FinalVerdict.SAFE:
            poisoned_marked_safe.append(entry.skill_id)

        table.add_row(
            entry.skill_id,
            entry.kind,
            _verdict_markup(report.final_verdict),
            str(report.trust_score),
            entry.expected_verdict or "—",
            str(injection) if injection else "—",
            result,
        )
        reports.append(
            {
                "skill_id": entry.skill_id,
                "version": entry.version,
                "kind": entry.kind,
                "label": entry.label,
                "content_hash": report.content_hash,
                "content_hash_indexed": entry.content_hash,
                "expected_verdict": entry.expected_verdict,
                "verdict": verdict,
                "trust_score": report.trust_score,
                "injection_flags": [f.model_dump() for f in report.stage1.injection_flags],
                "evidence_hash": report.evidence_hash,
                "provenance": {
                    "source": entry.provenance.source,
                    "source_url": entry.provenance.source_url,
                    "fetched_at": entry.provenance.fetched_at,
                },
            }
        )

    console.print(table)
    console.print(
        f"\nAudited [bold]{len(entries)}[/bold] entries; "
        f"{sum(1 for e in entries if e.is_poisoned)} poisoned, "
        f"{sum(1 for e in entries if e.label == 'safe')} safe fixtures."
    )

    if json_out:
        Path(json_out).write_text(
            json.dumps({"reports": reports}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        console.print(f"Wrote reports to {json_out}")

    # A poisoned fixture coming back SAFE is a hard failure regardless of --strict.
    failed = False
    if poisoned_marked_safe:
        console.print("[bold red]POISONED FIXTURE MARKED SAFE:[/bold red]")
        for skill_id in poisoned_marked_safe:
            console.print(f"  [red]x[/red] {skill_id}")
        failed = True
    if strict and mismatches:
        console.print("[bold yellow]Expected-verdict mismatches:[/bold yellow]")
        for mismatch in mismatches:
            console.print(f"  [yellow]![/yellow] {mismatch}")
        failed = True
    if failed:
        raise SystemExit(1)


def _load_existing(corpus: Corpus) -> dict[str, CorpusEntry]:
    if corpus.index_path.exists():
        return {e.skill_id: e for e in corpus.load()}
    return {}


def _verdict_markup(verdict: FinalVerdict) -> str:
    color = {
        FinalVerdict.SAFE: "green",
        FinalVerdict.WARNING: "yellow",
        FinalVerdict.DANGEROUS: "red",
    }[verdict]
    return f"[{color}]{verdict.value}[/{color}]"


__all__ = ["intake", "audit_corpus"]
