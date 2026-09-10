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

from sterish_pipeline import specs
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


# Registered on the group, not a bare click.command: as a loose command it was
# never reachable through `intake`, so the batch audit the ticket asks for could
# not be invoked at all.
@intake.command("audit-corpus")
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
        injection = len(report.stage1.injection_findings)
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
                "injection_findings": [f.model_dump() for f in report.stage1.injection_findings],
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


@intake.command("seed")
@click.option("--corpus", "corpus_dir", default=str(DEFAULT_CORPUS), type=click.Path())
@click.option("--config", "-c", default=None, help="Pipeline config JSON")
@click.option(
    "--label",
    "labels",
    multiple=True,
    default=("catalog",),
    help="Corpus labels to seed. Repeatable. Default: catalog.",
)
@click.option(
    "--exclude",
    "excluded",
    multiple=True,
    help="skill_id to hold back. Repeatable. Use for a known false positive that "
    "must not be published as a verdict.",
)
@click.option("--reports-dir", default="reports", help="Where published reports are written")
@click.option("--report-base-url", default="", help="Public base URL for report_uri")
@click.option("--journal", default=".sterish-journal.json", help="Orchestrator journal path")
@click.option("--json-out", type=click.Path(), default=None, help="Write the run log as JSON")
@click.option("--dry-run", is_flag=True, help="Audit and validate, but sign nothing")
@click.option(
    "--allow-dangerous",
    is_flag=True,
    help="Also seed entries that audit DANGEROUS. Off by default: publishing a DANGEROUS "
    "verdict against a third party's skill is an accusation, and an unreviewed batch is "
    "not the place to make one.",
)
def seed(
    corpus_dir: str,
    config: str | None,
    labels: tuple[str, ...],
    excluded: tuple[str, ...],
    reports_dir: str,
    report_base_url: str,
    journal: str,
    json_out: str | None,
    dry_run: bool,
    allow_dangerous: bool,
) -> None:
    """Audit corpus entries and land each verdict on chain.

    The batch path `submit` never had: `submit` takes one skill directory, so seeding a
    corpus meant a shell loop that could not see the corpus manifest, could not reuse the
    frozen `content_hash`, and had nowhere to record what it had already done.

    Every entry is audited, its document validated against the frozen schema, and only
    then submitted. A failure on one entry is recorded and the run continues, because
    stopping halfway through a batch of on-chain writes leaves the worst possible state:
    some skills registered, no record of which.
    """
    import os
    import time

    from sterish_pipeline.audit import to_verdict_json
    from sterish_pipeline.orchestrator import OrchestratorConfig, orchestrate
    from sterish_pipeline.stages.stage3_verdict_synthesis import build_verdict_document

    cfg = PipelineConfig.load(config)
    for name, value in (
        ("registry_contract_id", os.getenv("REGISTRY_CA")),
        ("rpc_url", os.getenv("STELLAR_RPC_URL")),
        ("network_passphrase", os.getenv("STELLAR_NETWORK_PASSPHRASE")),
    ):
        if value:
            setattr(cfg, name, value)

    if not dry_run:
        missing = [
            k for k in ("REGISTRY_CA", "DEVELOPER_SECRET", "AUDITOR_SECRET") if not os.getenv(k)
        ]
        if missing:
            raise click.ClickException(f"missing environment variables: {', '.join(missing)}")

    corpus = Corpus(corpus_dir)
    wanted = set(labels)
    held_back = set(excluded)
    entries = [e for e in sorted(corpus.load(), key=lambda e: e.skill_id) if e.label in wanted]
    if not entries:
        console.print(f"[red]no corpus entries with label(s) {sorted(wanted)}[/red]")
        raise SystemExit(1)

    orch_config = OrchestratorConfig(
        registry_id=cfg.registry_contract_id,
        tokens_id=os.getenv("TOKENS_CA", ""),
        escrow_id=os.getenv("ESCROW_CA", ""),
        owner_secret=os.getenv("DEVELOPER_SECRET", ""),
        auditor_secret=os.getenv("AUDITOR_SECRET", ""),
        admin_secret=os.getenv("DEPLOYER_SECRET", ""),
        reports_dir=Path(reports_dir),
        report_base_url=report_base_url,
        journal_path=Path(journal),
        run_escrow=False,
    )

    table = Table("skill_id", "verdict", "score", "seconds", "result")
    log: list[dict] = []
    failures: list[str] = []

    for entry in entries:
        if entry.skill_id in held_back:
            table.add_row(entry.skill_id, "—", "—", "—", "[yellow]held back[/yellow]")
            log.append({"skill_id": entry.skill_id, "status": "held_back"})
            continue

        started = time.monotonic()
        skill = corpus.normalized(entry)
        report = audit_normalized(skill, config=cfg, skip_sandbox=True)

        # The frozen content_hash from the index, not a recomputation: the corpus is the
        # thing being attested to, and hashing it twice invites the two to disagree.
        document = build_verdict_document(report, skill.manifest, entry.content_hash, cfg)
        payload = to_verdict_json(document)

        verdict = payload["verdict"]
        score = payload["score"]

        if verdict == FinalVerdict.DANGEROUS.value and not allow_dangerous:
            elapsed = time.monotonic() - started
            table.add_row(
                entry.skill_id, _verdict_markup(FinalVerdict.DANGEROUS), str(score),
                f"{elapsed:.1f}", "[yellow]skipped (DANGEROUS)[/yellow]",
            )
            log.append(
                {"skill_id": entry.skill_id, "status": "skipped_dangerous",
                 "verdict": verdict, "score": score}
            )
            continue

        try:
            specs.validate_verdict_document(payload, submittable=True)
        except Exception as exc:  # noqa: BLE001 - reported per entry, run continues
            failures.append(f"{entry.skill_id}: document invalid: {exc}")
            table.add_row(entry.skill_id, verdict, str(score), "—", "[red]invalid[/red]")
            log.append({"skill_id": entry.skill_id, "status": "invalid", "error": str(exc)})
            continue

        if dry_run:
            elapsed = time.monotonic() - started
            table.add_row(
                entry.skill_id, verdict, str(score), f"{elapsed:.1f}", "[cyan]dry-run[/cyan]"
            )
            log.append(
                {"skill_id": entry.skill_id, "status": "dry_run",
                 "verdict": verdict, "score": score,
                 "content_hash": payload["content_hash"], "seconds": round(elapsed, 1)}
            )
            continue

        try:
            result = orchestrate(payload, orch_config, cfg)
        except Exception as exc:  # noqa: BLE001 - one bad entry must not end the batch
            failures.append(f"{entry.skill_id}: {exc}")
            table.add_row(entry.skill_id, verdict, str(score), "—", "[red]error[/red]")
            log.append({"skill_id": entry.skill_id, "status": "error", "error": str(exc)})
            continue

        elapsed = time.monotonic() - started
        row = result.to_dict()
        row["seconds"] = round(elapsed, 1)
        row["tx"] = result.tx_hashes()
        log.append(row)

        if not result.ok:
            failures.append(f"{entry.skill_id}: orchestration incomplete")
        table.add_row(
            entry.skill_id, verdict, str(score), f"{elapsed:.1f}",
            "[green]on chain[/green]" if result.ok else "[red]incomplete[/red]",
        )

    console.print(table)

    seeded = [r for r in log if r.get("ok")]
    console.print(
        f"\n{len(seeded)} on chain, "
        f"{sum(1 for r in log if r.get('status') == 'held_back')} held back, "
        f"{sum(1 for r in log if r.get('status') == 'skipped_dangerous')} skipped DANGEROUS, "
        f"{len(failures)} failed."
    )
    slow = [r for r in log if (r.get("seconds") or 0) > 300]
    if slow:
        # delivery-plan criterion: under five minutes per skill.
        console.print(f"[yellow]{len(slow)} entries took over 5 minutes[/yellow]")

    if json_out:
        Path(json_out).write_text(json.dumps(log, indent=2), encoding="utf-8")
        console.print(f"Wrote run log to {json_out}")

    if failures:
        console.print("[bold red]Failures:[/bold red]")
        for failure in failures:
            console.print(f"  [red]x[/red] {failure}")
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


__all__ = ["intake", "audit_corpus", "seed"]
