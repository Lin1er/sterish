"""STE-16 integration tests against the live testnet deployment (STE-13).

Opt-in: they submit real transactions and move real testnet balances, so they are
skipped unless STERISH_LIVE_TESTS=1. One command, from the repo root:

    set -a && . ./.env && set +a
    cd pipeline && STERISH_LIVE_TESTS=1 \
        uv run --extra dev pytest tests/test_live_orchestration.py -v

Add STERISH_LIVE_ESCROW=1 to also exercise create_audit_request -> post_bond ->
settle/slash. That path runs against ESCROW_REHEARSAL_CA, which is wired to an asset
we control: the canonical escrow uses real testnet USDC, obtainable only from the
Circle faucet, which is web-only with a Captcha and cannot be scripted (recorded in
docs/deployments.md by STE-13). The contract code and actors are identical; only the
asset address differs.

Every skill registered here uses a timestamped id, so a run never collides with a
previous one and `register_skill` is genuinely exercised each time.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from sterish_pipeline import onchain, orchestrator, reports
from sterish_pipeline.audit import run_audit
from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.orchestrator import OrchestratorConfig, Step

pytestmark = pytest.mark.skipif(
    os.getenv("STERISH_LIVE_TESTS") != "1",
    reason="set STERISH_LIVE_TESTS=1 (and load .env) to run against testnet",
)

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_ESCROW = os.getenv("STERISH_LIVE_ESCROW") == "1"


@pytest.fixture(scope="module")
def pipeline_cfg() -> PipelineConfig:
    return PipelineConfig(
        registry_contract_id=os.environ["REGISTRY_CA"],
        rpc_url=os.environ["STELLAR_RPC_URL"],
        network_passphrase=os.environ["STELLAR_NETWORK_PASSPHRASE"],
        use_llm=False,          # deterministic: no key needed, no model variance
    )


@pytest.fixture
def orch_cfg(tmp_path) -> OrchestratorConfig:
    return OrchestratorConfig(
        registry_id=os.environ["REGISTRY_CA"],
        tokens_id=os.environ["TOKENS_CA"],
        escrow_id=os.environ.get("ESCROW_REHEARSAL_CA", ""),
        owner_secret=os.environ["DEVELOPER_SECRET"],
        auditor_secret=os.environ["AUDITOR_SECRET"],
        admin_secret=os.environ["DEPLOYER_SECRET"],
        reports_dir=tmp_path / "reports",
        journal_path=tmp_path / "journal.json",
        run_escrow=LIVE_ESCROW,
    )


def _fresh_skill(tmp_path: Path, fixture: str) -> tuple[Path, str]:
    """Copy a fixture under a unique skill_id so each run registers new bytes.

    The fixture directory name is sanitised: the frozen verdict schema's skill_id
    pattern allows only lowercase alphanumerics, hyphens and dots, so an underscore
    from a directory name would fail validation before anything reached the chain.
    """
    slug = fixture.replace("_", "-")
    skill_id = f"com.sterish.it-{slug}-{int(time.time())}"
    skill_dir = tmp_path / "skill"
    shutil.copytree(FIXTURES / fixture, skill_dir)

    manifest_path = skill_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["skill_id"] = skill_id
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return skill_dir, skill_id


def _audit(skill_dir: Path, cfg: PipelineConfig) -> dict:
    run = run_audit(skill_dir, config=cfg, skip_sandbox=True)
    run.validate(submittable=True)
    return run.verdict_json()


def test_safe_skill_lands_on_chain_end_to_end(tmp_path, pipeline_cfg, orch_cfg):
    """register -> submit_verdict -> mint_verified, then verified by reading back."""
    skill_dir, skill_id = _fresh_skill(tmp_path, "safe_skill")
    document = _audit(skill_dir, pipeline_cfg)
    assert document["verdict"] == "SAFE"

    result = orchestrator.orchestrate(document, orch_cfg, pipeline_cfg)
    assert result.ok, [s.to_dict() for s in result.steps]

    done = {str(s.step): s for s in result.steps}
    assert done[Step.REGISTER].status == "done"
    assert done[Step.VERDICT].status == "done"
    assert done[Step.MINT].status == "done"
    for step in (Step.REGISTER, Step.VERDICT, Step.MINT):
        assert len(done[step].tx_hash) == 64

    # Read the answer back from the chain, not from our own result object.
    record = onchain.lookup_by_hash(pipeline_cfg, orch_cfg.registry_id, document["content_hash"])
    assert record is not None
    assert record["skill_id"] == skill_id
    assert record["verdict"] == ["Safe"]
    assert record["trust_score"] == document["score"]
    assert onchain.is_verified(pipeline_cfg, orch_cfg.registry_id, skill_id, document["version"])


def test_published_report_hashes_to_the_on_chain_evidence(tmp_path, pipeline_cfg, orch_cfg):
    """The check a third party performs before trusting a report."""
    skill_dir, skill_id = _fresh_skill(tmp_path, "safe_skill")
    document = _audit(skill_dir, pipeline_cfg)
    result = orchestrator.orchestrate(document, orch_cfg, pipeline_cfg)

    record = onchain.get_version(pipeline_cfg, orch_cfg.registry_id, skill_id, document["version"])
    assert record["evidence_hash"].hex() == result.evidence_hash

    report_path = orch_cfg.reports_dir / skill_id / f"{document['version']}.json"
    assert reports.verify(report_path, result.evidence_hash)


def test_poisoned_skill_is_dangerous_and_never_gets_a_badge(tmp_path, pipeline_cfg, orch_cfg):
    """The claim the project exists to make, proven on chain."""
    skill_dir, skill_id = _fresh_skill(tmp_path, "poisoned_pdf_skill")
    document = _audit(skill_dir, pipeline_cfg)
    assert document["verdict"] == "DANGEROUS"

    result = orchestrator.orchestrate(document, orch_cfg, pipeline_cfg)
    assert result.ok, [s.to_dict() for s in result.steps]

    mint = next(s for s in result.steps if s.step == Step.MINT)
    assert mint.status == "skipped" and mint.tx_hash is None

    record = onchain.lookup_by_hash(pipeline_cfg, orch_cfg.registry_id, document["content_hash"])
    assert record["verdict"] == ["Dangerous"]
    verified = onchain.is_verified(
        pipeline_cfg, orch_cfg.registry_id, skill_id, document["version"]
    )
    assert verified is False

    # The contract refuses the badge too, independently of the orchestrator.
    badge = onchain.simulate(
        pipeline_cfg, orch_cfg.tokens_id, "is_verified_token",
        [onchain.scval.to_string(skill_id), onchain.scval.to_string(document["version"])],
    )
    assert badge is False


def test_rerunning_is_idempotent(tmp_path, pipeline_cfg, orch_cfg):
    """A second run must not re-register, re-submit an identical verdict, or re-mint."""
    skill_dir, _ = _fresh_skill(tmp_path, "safe_skill")
    document = _audit(skill_dir, pipeline_cfg)

    first = orchestrator.orchestrate(document, orch_cfg, pipeline_cfg)
    assert first.ok

    second = orchestrator.orchestrate(document, orch_cfg, pipeline_cfg)
    statuses = {str(s.step): s.status for s in second.steps}
    assert statuses[Step.REGISTER] == "skipped"
    assert statuses[Step.VERDICT] == "skipped"
    assert statuses[Step.MINT] == "skipped"

    # No new transaction for any of the chain-state steps.
    chain_steps = (Step.REGISTER, Step.VERDICT, Step.MINT)
    assert not any(s.tx_hash for s in second.steps if s.step in chain_steps)

    # The escrow job is skipped too, because re-opening one would lock another fee
    # and bond. That guard is journal-based; see _run_escrow.
    if LIVE_ESCROW:
        assert statuses[Step.CREATE_REQUEST] == "skipped"
        assert Step.SETTLE not in statuses and Step.SLASH not in statuses


def test_registering_the_same_hash_under_a_new_id_is_refused(tmp_path, pipeline_cfg, orch_cfg):
    """Hash squatting is impossible: one content_hash maps to one (skill_id, version)."""
    skill_dir, _ = _fresh_skill(tmp_path, "safe_skill")
    document = _audit(skill_dir, pipeline_cfg)
    orchestrator.orchestrate(document, orch_cfg, pipeline_cfg)

    with pytest.raises(onchain.ContractCallError) as exc:
        onchain.register_skill(
            pipeline_cfg, orch_cfg.registry_id, orch_cfg.owner_secret,
            "com.someone.else", "1.0.0", document["content_hash"],
        )
    assert exc.value.code == 6  # HashAlreadyRegistered


@pytest.mark.skipif(not LIVE_ESCROW, reason="set STERISH_LIVE_ESCROW=1 to move balances")
def test_safe_skill_settles_the_escrow(tmp_path, pipeline_cfg, orch_cfg):
    skill_dir, _ = _fresh_skill(tmp_path, "safe_skill")
    document = _audit(skill_dir, pipeline_cfg)

    result = orchestrator.orchestrate(document, orch_cfg, pipeline_cfg)
    assert result.ok, [s.to_dict() for s in result.steps]

    statuses = {str(s.step): s.status for s in result.steps}
    assert statuses[Step.CREATE_REQUEST] == "done"
    assert statuses[Step.POST_BOND] == "done"
    assert statuses[Step.SETTLE] == "done"
    assert Step.SLASH not in statuses


@pytest.mark.skipif(not LIVE_ESCROW, reason="set STERISH_LIVE_ESCROW=1 to move balances")
def test_dangerous_skill_slashes_the_bond(tmp_path, pipeline_cfg, orch_cfg):
    skill_dir, _ = _fresh_skill(tmp_path, "poisoned_pdf_skill")
    document = _audit(skill_dir, pipeline_cfg)
    assert document["verdict"] == "DANGEROUS"

    result = orchestrator.orchestrate(document, orch_cfg, pipeline_cfg)
    assert result.ok, [s.to_dict() for s in result.steps]

    statuses = {str(s.step): s.status for s in result.steps}
    assert statuses[Step.SLASH] == "done"
    assert Step.SETTLE not in statuses
    assert statuses[Step.MINT] == "skipped"
