"""`intake seed --dry-run` says what a real run would write, per entry (STE-37).

Correcting the published cctp and price-checker verdicts, and re-anchoring every report
whose bytes moved with STE-39, is a batch of permanent writes. The dry run is the
rehearsal for it, so it has to name the action for each entry and the hash it would
anchor — and that hash has to be exactly the one a real run's `reports.publish` writes.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from sterish_pipeline import onchain, reports
from sterish_pipeline.cli import cli
from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.intake.cli import _dry_run_plan
from sterish_pipeline.intake.corpus import Corpus

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"
REGISTRY = "C" + "A" * 55


def _entry(skill_id):
    (entry,) = [e for e in Corpus(CORPUS_DIR).load() if e.skill_id == skill_id]
    return entry


def _cfg():
    cfg = PipelineConfig()
    cfg.registry_contract_id = REGISTRY
    return cfg


def _record(verdict, score, evidence_hash):
    return {
        "verdict": [verdict],
        "trust_score": score,
        "evidence_hash": bytes.fromhex(evidence_hash),
    }


H1 = "11" * 32
H2 = "22" * 32


@pytest.fixture
def price_checker():
    return _entry("com.fixtures.safe.price-checker")


def test_an_unregistered_version_plans_register_and_verdict(monkeypatch, price_checker):
    def missing(*_):
        raise onchain.ContractCallError(4, "get_version")  # VersionNotFound

    monkeypatch.setattr(onchain, "get_version", missing)
    plan = _dry_run_plan(_cfg(), price_checker, "SAFE", 90, H1)
    assert plan["action"] == "register+verdict"


def test_a_wrong_published_verdict_plans_a_verdict_update_naming_every_change(
    monkeypatch, price_checker
):
    monkeypatch.setattr(onchain, "get_version", lambda *_: _record("Dangerous", 10, H2))
    plan = _dry_run_plan(_cfg(), price_checker, "SAFE", 90, H1)
    assert plan["action"] == "verdict"
    assert plan["changes"] == ["verdict", "score", "evidence_hash"]
    assert plan["chain"] == {"verdict": "DANGEROUS", "score": 10, "evidence_hash": H2}


def test_a_moved_report_alone_is_still_an_update(monkeypatch, price_checker):
    """The STE-39 re-anchor: same verdict, same score, different bytes."""
    monkeypatch.setattr(onchain, "get_version", lambda *_: _record("Safe", 90, H2))
    plan = _dry_run_plan(_cfg(), price_checker, "SAFE", 90, H1)
    assert (plan["action"], plan["changes"]) == ("verdict", ["evidence_hash"])


def test_an_identical_record_is_a_noop(monkeypatch, price_checker):
    monkeypatch.setattr(onchain, "get_version", lambda *_: _record("Safe", 90, H1))
    assert _dry_run_plan(_cfg(), price_checker, "SAFE", 90, H1)["action"] == "noop"


def test_an_rpc_failure_is_unknown_not_a_guess(monkeypatch, price_checker):
    def down(*_):
        raise onchain.OnChainError("RPC call to get_version failed: timeout")

    monkeypatch.setattr(onchain, "get_version", down)
    plan = _dry_run_plan(_cfg(), price_checker, "SAFE", 90, H1)
    assert plan["action"] == "unknown"
    assert "timeout" in plan["chain_error"]


def test_no_registry_is_unknown(price_checker):
    assert _dry_run_plan(PipelineConfig(), price_checker, "SAFE", 90, H1)["action"] == "unknown"


def test_the_dry_run_anchors_exactly_what_a_real_run_would_publish(
    monkeypatch, tmp_path, price_checker
):
    reads = []

    def record_read(cfg, registry_id, skill_id, version):
        reads.append((registry_id, skill_id, version))
        return _record("Dangerous", 10, H2)

    monkeypatch.setattr(onchain, "get_version", record_read)
    monkeypatch.setattr(onchain, "invoke", lambda *a, **k: pytest.fail("dry run signed"))
    monkeypatch.setenv("REGISTRY_CA", REGISTRY)
    out = tmp_path / "plan.json"
    result = CliRunner().invoke(
        cli,
        [
            "intake",
            "seed",
            "--corpus",
            str(CORPUS_DIR),
            "--label",
            "safe",
            "--dry-run",
            "--reports-dir",
            str(tmp_path / "reports"),
            "--json-out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "reports").exists()  # a dry run writes no report either

    rows = {row["skill_id"]: row for row in json.loads(out.read_text())}
    row = rows["com.fixtures.safe.price-checker"]
    assert (row["verdict"], row["score"], row["action"]) == ("SAFE", 90, "verdict")
    assert (REGISTRY, price_checker.skill_id, price_checker.version) in reads

    # Rebuild the document the way a real run does and publish it for real.
    from sterish_pipeline.audit import audit_normalized, to_verdict_json
    from sterish_pipeline.stages.stage3_verdict_synthesis import build_verdict_document

    corpus = Corpus(CORPUS_DIR)
    skill = corpus.normalized(price_checker)
    report = audit_normalized(skill, config=PipelineConfig.load(None), skip_sandbox=True)
    payload = to_verdict_json(
        build_verdict_document(
            report, skill.manifest, price_checker.content_hash, PipelineConfig.load(None)
        )
    )
    published = reports.publish(
        payload, price_checker.skill_id, price_checker.version, tmp_path / "real"
    )
    assert row["evidence_hash"] == published.evidence_hash


def test_a_register_only_entry_plans_register_or_nothing(monkeypatch):
    (entry,) = [e for e in Corpus(CORPUS_DIR).load() if e.register_only]

    def missing(*_):
        raise onchain.ContractCallError(4, "get_version")

    monkeypatch.setattr(onchain, "get_version", missing)
    assert _dry_run_plan(_cfg(), entry, None, None, None)["action"] == "register"

    monkeypatch.setattr(onchain, "get_version", lambda *_: _record("Unaudited", 0, "00" * 32))
    assert _dry_run_plan(_cfg(), entry, None, None, None)["action"] == "noop"


def _dry_run_rows(monkeypatch, tmp_path, *extra):
    monkeypatch.setattr(onchain, "get_version", lambda *_: _record("Safe", 100, H1))
    monkeypatch.setattr(onchain, "invoke", lambda *a, **k: pytest.fail("dry run signed"))
    monkeypatch.setenv("REGISTRY_CA", REGISTRY)
    out = tmp_path / "plan.json"
    result = CliRunner().invoke(
        cli,
        ["intake", "seed", "--corpus", str(CORPUS_DIR), "--dry-run",
         "--json-out", str(out), *extra],
    )
    assert result.exit_code == 0, result.output
    return {(r["skill_id"], r["version"]): r for r in json.loads(out.read_text())}, result.output


def test_allow_dangerous_marks_every_dangerous_row_as_intended(monkeypatch, tmp_path):
    rows, output = _dry_run_rows(
        monkeypatch, tmp_path, "--label", "poisoned", "--label", "demo", "--allow-dangerous"
    )
    dangerous = {k: r for k, r in rows.items() if r.get("verdict") == "DANGEROUS"}
    assert len(dangerous) == 5  # four poisoned fixtures + the release-notes rug pull
    for key, row in dangerous.items():
        assert row["status"] == "dry_run", key
        assert row["dangerous_intended"] is True, key
        assert "expected_verdict DANGEROUS" in row["dangerous_reason"]
    others = [r for r in rows.values() if r["verdict"] != "DANGEROUS"]
    assert not any(r.get("dangerous_intended") for r in others)
    assert "5 DANGEROUS on purpose" in output


def test_without_the_flag_dangerous_rows_are_skipped_with_a_reason(monkeypatch, tmp_path):
    rows, _ = _dry_run_rows(monkeypatch, tmp_path, "--label", "poisoned")
    assert {r["status"] for r in rows.values()} == {"skipped_dangerous"}
    assert all(r["reason"] == "--allow-dangerous not given" for r in rows.values())


def test_the_flag_never_publishes_a_dangerous_verdict_the_corpus_did_not_expect(
    monkeypatch, tmp_path
):
    """Simulate the detector regressing on a catalogue skill: the flag must not carry it."""
    from sterish_pipeline.intake import cli as intake_cli
    from sterish_pipeline.models import FinalVerdict

    real = intake_cli.audit_normalized

    def cctp_regresses(skill, **kwargs):
        report = real(skill, **kwargs)
        if skill.manifest.name and "cctp" in str(skill.manifest.name).lower():
            report.final_verdict = FinalVerdict.DANGEROUS
            report.trust_score = 10
        return report

    monkeypatch.setattr(intake_cli, "audit_normalized", cctp_regresses)
    rows, _ = _dry_run_rows(monkeypatch, tmp_path, "--label", "catalog", "--allow-dangerous")
    cctp = rows[("org.stellar.skills.cross-chain.cctp", "2026.8.31")]
    assert cctp["status"] == "skipped_dangerous"
    assert "not DANGEROUS" in cctp["reason"]
