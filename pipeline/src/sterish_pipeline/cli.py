"""Command line entry point.

``sterish audit <skill>`` runs all three stages and prints the frozen verdict document.
The command deliberately takes a **skill directory**, not just a manifest: ``content_hash``
is computed over the whole directory and ``SKILL.md`` is part of the text stage 1 scans, so
auditing a lone manifest.json audits less than the user is about to install.
"""

import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sterish_pipeline.audit import run_audit
from sterish_pipeline.config import PipelineConfig

console = Console()
logger = logging.getLogger("sterish")

_VERDICT_COLOR = {"SAFE": "green", "WARNING": "yellow", "DANGEROUS": "red", "UNAUDITED": "dim"}


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """Sterish: Audited Skill Marketplace Audit Pipeline."""
    _setup_logging(verbose)


@cli.command()
@click.argument("skill", type=click.Path(exists=True), required=False)
@click.option(
    "--manifest",
    "-m",
    type=click.Path(exists=True),
    default=None,
    help="Path to the skill directory or its manifest.json (alias for the SKILL argument)",
)
@click.option("--skill-id", default=None, help="Expected skill id; fails if the manifest differs")
@click.option("--config", "-c", default=None, help="Path to pipeline config JSON")
@click.option("--skip-sandbox", is_flag=True, help="Skip stage 2 sandbox check")
@click.option("--no-llm", is_flag=True, help="Deterministic only: never call the model")
@click.option("--out", "-o", default=None, help="Write the verdict JSON to this path")
@click.option("--json", "as_json", is_flag=True, help="Print only the verdict JSON")
def audit(
    skill: str | None,
    manifest: str | None,
    skill_id: str | None,
    config: str | None,
    skip_sandbox: bool,
    no_llm: bool,
    out: str | None,
    as_json: bool,
) -> None:
    """Run the full 3-stage audit pipeline over a skill."""
    target = skill or manifest
    if target is None:
        raise click.UsageError("give a skill directory (or --manifest path/to/manifest.json)")

    cfg = PipelineConfig.load(config)
    if no_llm:
        cfg = cfg.model_copy(update={"use_llm": False})

    run = run_audit(target, cfg, skip_sandbox=skip_sandbox)
    document = run.verdict_json()

    if skill_id is not None and skill_id != run.manifest.skill_id:
        console.print(
            f"[red]Error: manifest declares skill_id {run.manifest.skill_id!r}, "
            f"but --skill-id says {skill_id!r}.[/red]"
        )
        sys.exit(2)

    # The schema is the contract with the submitter, the API and the dashboard. Emitting a
    # document that does not satisfy it is a failure, not a warning.
    try:
        run.validate(submittable=True)
    except ValueError as exc:
        console.print(f"[red]Emitted document failed the frozen schema: {exc}[/red]")
        sys.exit(3)

    if out:
        Path(out).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    if as_json:
        click.echo(json.dumps(document, indent=2))
        sys.exit(0 if document["verdict"] == "SAFE" else 1)

    console.print(f"[bold]Auditing:[/] {run.manifest.name} v{run.manifest.version}")
    console.print(f"[dim]Skill ID:[/] {run.manifest.skill_id}")
    console.print(f"[dim]content_hash:[/] {run.content_hash}")

    stage1 = run.report.stage1
    console.print(
        f"\n[bold cyan]Stage 1:[/] {len(stage1.risk_flags)} declared-capability flag(s), "
        f"{len(stage1.injection_findings)} injection finding(s) "
        f"across {stage1.text_scanned} text field(s)"
    )
    if stage1.injection_findings:
        table = Table("Pattern", "Severity", "Where", "Evidence")
        for finding in stage1.injection_findings:
            table.add_row(
                finding.pattern_id,
                finding.severity.value,
                finding.field_path,
                finding.snippet[:70],
            )
        console.print(table)

    stage2 = run.report.stage2
    console.print(
        f"\n[bold cyan]Stage 2:[/] {len(stage2.behavioral_flags)} behavioral flag(s), "
        f"escaped_sandbox={stage2.escaped_sandbox}"
    )

    console.print("\n[bold cyan]Stage 3:[/] synthesis")
    for reason in run.report.policy_reasons:
        console.print(f"  [dim]- {reason}[/dim]")
    for note in run.report.llm_notes:
        console.print(f"  [dim]- {note}[/dim]")

    color = _VERDICT_COLOR[document["verdict"]]
    console.print(
        Panel(
            f"[bold {color}]{document['verdict']}[/bold {color}]  "
            f"risk={document['risk']}  recommendation={document['recommendation']}\n"
            f"Trust Score: {document['score']}/100\n"
            f"Capabilities: {', '.join(document['capabilities']) or 'none'}\n"
            f"Findings: {len(document['findings'])}\n"
            f"Evidence Hash: {document['evidence_hash'][:16]}...\n"
            f"{run.report.recommendation}",
            title="Audit Result",
        )
    )
    if out:
        console.print(f"[dim]verdict JSON written to {out}[/dim]")

    sys.exit(0 if document["verdict"] == "SAFE" else 1)


@cli.command()
@click.argument("skill", type=click.Path(exists=True))
def hash(skill: str) -> None:
    """Print the canonical content_hash v1 of a skill directory."""
    from sterish_pipeline import specs

    click.echo(specs.hash_dir(skill))


@cli.command()
@click.argument("skill", type=click.Path(exists=True))
@click.option("--config", "-c", default=None, help="Path to pipeline config JSON")
@click.option("--skip-sandbox", is_flag=True, help="Skip stage 2 sandbox check")
@click.option("--no-llm", is_flag=True, help="Deterministic only: never call the model")
@click.option("--reports-dir", default="reports", help="Where the published report is written")
@click.option("--report-base-url", default="", help="Public base URL for report_uri")
@click.option("--journal", default=".sterish-journal.json", help="Resume journal path")
@click.option("--escrow/--no-escrow", default=False,
              help="Also run create_audit_request -> post_bond -> settle/slash")
@click.option("--dry-run", is_flag=True, help="Resolve everything but submit nothing")
def submit(skill, config, skip_sandbox, no_llm, reports_dir, report_base_url,
           journal, escrow, dry_run) -> None:
    """Audit SKILL and land the verdict on chain.

    Reads contract addresses and signers from the environment (see .env.example);
    secrets are never accepted as flags, so they cannot end up in shell history.
    """
    import os

    from sterish_pipeline.orchestrator import OrchestratorConfig, orchestrate

    cfg = PipelineConfig.load(config)
    if no_llm:
        cfg.use_llm = False
    for name, value in (
        ("registry_contract_id", os.getenv("REGISTRY_CA")),
        ("rpc_url", os.getenv("STELLAR_RPC_URL")),
        ("network_passphrase", os.getenv("STELLAR_NETWORK_PASSPHRASE")),
    ):
        if value:
            setattr(cfg, name, value)

    missing = [k for k in ("REGISTRY_CA", "DEVELOPER_SECRET", "AUDITOR_SECRET") if not os.getenv(k)]
    if missing:
        raise click.ClickException(f"missing environment variables: {', '.join(missing)}")

    run = run_audit(skill, config=cfg, skip_sandbox=skip_sandbox)
    run.validate(submittable=True)
    document = run.verdict_json()

    result = orchestrate(
        document,
        OrchestratorConfig(
            registry_id=os.environ["REGISTRY_CA"],
            tokens_id=os.getenv("TOKENS_CA", ""),
            escrow_id=os.getenv("ESCROW_CA", ""),
            owner_secret=os.environ["DEVELOPER_SECRET"],
            auditor_secret=os.environ["AUDITOR_SECRET"],
            admin_secret=os.getenv("DEPLOYER_SECRET", ""),
            reports_dir=Path(reports_dir),
            report_base_url=report_base_url,
            journal_path=Path(journal),
            run_escrow=escrow,
        ),
        cfg,
        dry_run=dry_run,
    )

    click.echo(f"{result.skill_id}@{result.version}  {result.verdict}  score={result.score}")
    for step in result.steps:
        line = f"  {str(step.step):<22} {step.status}"
        if step.tx_hash:
            line += f"  {step.tx_url}"
        elif step.detail:
            line += f"  ({step.detail})"
        click.echo(line)
    if result.evidence_hash:
        click.echo(f"  evidence_hash          {result.evidence_hash}")
        click.echo(f"  report_uri             {result.report_uri}")
    if not result.ok:
        raise click.ClickException("orchestration did not complete cleanly")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
