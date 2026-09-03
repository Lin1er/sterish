import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import AuditReport, SkillManifest
from sterish_pipeline.stages import run_sandbox_check, scan_description, synthesize_verdict

console = Console()
logger = logging.getLogger("sterish")


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
@click.option("--skill-id", required=True, help="Unique skill identifier")
@click.option(
    "--manifest",
    "-m",
    required=True,
    type=click.Path(exists=True),
    help="Path to skill manifest JSON",
)
@click.option("--config", "-c", default=None, help="Path to pipeline config JSON")
@click.option("--skip-sandbox", is_flag=True, help="Skip stage 2 sandbox check")
@click.option("--submit", is_flag=True, help="Submit verdict on-chain after audit")
@click.option(
    "--secret-key", envvar="STERISH_SECRET_KEY", help="Stellar secret key for on-chain submission"
)
def audit(
    skill_id: str,
    manifest: str,
    config: str | None,
    skip_sandbox: bool,
    submit: bool,
    secret_key: str | None,
) -> None:
    """Run the full 3-stage audit pipeline on a skill manifest."""
    cfg = PipelineConfig.load(config)

    # Load manifest.
    manifest_path = Path(manifest)
    manifest_data = json.loads(manifest_path.read_text())
    skill_manifest = SkillManifest.model_validate(manifest_data)
    console.print(f"[bold]Auditing:[/] {skill_manifest.name} v{skill_manifest.version}")
    console.print(f"[dim]Skill ID:[/] {skill_id}")

    report = AuditReport(skill_id=skill_id)

    # Stage 1: Description scanning.
    console.print("\n[bold cyan]Stage 1:[/] Scanning tool descriptions...")
    stage1 = scan_description(skill_manifest, cfg)
    console.print(f"  Score: {stage1.initial_score}/100")
    if stage1.risk_flags:
        table = Table("Capability", "Severity", "Description")
        for flag in stage1.risk_flags:
            table.add_row(flag.capability.value, flag.severity.value, flag.description)
        console.print(table)
    else:
        console.print("  [green]No risk flags detected.[/green]")

    if stage1.injection_flags:
        console.print(
            f"  [bold red]{len(stage1.injection_flags)} injection finding(s) "
            f"in the skill's own text:[/bold red]"
        )
        inj_table = Table("Severity", "Rule", "Location", "Evidence")
        for flag in stage1.injection_flags:
            inj_table.add_row(flag.severity.value, flag.rule, flag.location, flag.evidence)
        console.print(inj_table)

    # Stage 2: Sandbox check.
    if skip_sandbox:
        console.print("\n[bold cyan]Stage 2:[/] [dim]Skipped (--skip-sandbox)[/dim]")
        from sterish_pipeline.models import Stage2Result

        stage2 = Stage2Result()
    else:
        console.print("\n[bold cyan]Stage 2:[/] Running sandbox check...")
        stage2 = run_sandbox_check(skill_manifest, config=cfg)
        if stage2.escaped_sandbox:
            console.print("  [bold red]SANDBOX ESCAPED![/bold red]")
        elif stage2.behavioral_flags:
            console.print(f"  {len(stage2.behavioral_flags)} behavioral flag(s) found.")
        else:
            console.print("  [green]No behavioral violations.[/green]")

    # Stage 3: Verdict synthesis.
    console.print("\n[bold cyan]Stage 3:[/] Synthesizing verdict...")
    final_report = synthesize_verdict(report, stage1, stage2, cfg)

    # Display result.
    color = {
        "SAFE": "green",
        "WARNING": "yellow",
        "DANGEROUS": "red",
    }[final_report.final_verdict.value]
    console.print(
        Panel(
            f"[bold {color}]{final_report.final_verdict.value}[/bold {color}]\n"
            f"Trust Score: {final_report.trust_score}/100\n"
            f"Evidence Hash: {final_report.evidence_hash[:16]}...\n"
            f"{final_report.recommendation}",
            title="Audit Result",
        )
    )

    # Optionally submit on-chain.
    if submit:
        if not secret_key:
            console.print(
                "[red]Error: --secret-key or STERISH_SECRET_KEY required for "
                "on-chain submission.[/red]"
            )
            sys.exit(1)
        if not cfg.registry_contract_id:
            console.print("[red]Error: registry_contract_id not set in config.[/red]")
            sys.exit(1)
        try:
            from sterish_pipeline.onchain import submit_verdict_to_chain

            tx_hash = submit_verdict_to_chain(
                contract_id=cfg.registry_contract_id,
                skill_id=skill_id,
                verdict=final_report.final_verdict,
                score=final_report.trust_score,
                evidence_hash=final_report.evidence_hash,
                secret_key=secret_key,
                public_key="",  # derived from secret_key
            )
            console.print(f"[green]Verdict submitted on-chain. TX: {tx_hash}[/green]")
        except Exception as exc:
            console.print(f"[red]On-chain submission failed: {exc}[/red]")
            sys.exit(1)


@cli.command("hash")
@click.option(
    "--path",
    "root",
    required=True,
    type=click.Path(exists=True),
    help="Skill file or directory to hash",
)
def hash_command(root: str) -> None:
    """Compute content_hash v1 for a skill on disk (see docs/specs/content-hash.md).

    The hash covers only the skill's file paths and their normalized bytes —
    not skill_id or version.
    """
    from sterish_pipeline.content_hash import content_hash_path

    digest = content_hash_path(Path(root))
    console.print(digest)


def _register_subcommands() -> None:
    """Attach the intake group and corpus batch to the top-level CLI."""
    from sterish_pipeline.intake.cli import audit_corpus, intake

    cli.add_command(intake)
    cli.add_command(audit_corpus)


_register_subcommands()


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
