"""Orchestrator flow control, with the chain stubbed. No network."""

import pytest
from stellar_sdk import Keypair

from sterish_pipeline import onchain, orchestrator
from sterish_pipeline.orchestrator import Journal, OrchestratorConfig, Step

# Generated per run and never used to sign anything: every write is stubbed here.
# Hardcoding fake seeds does not work -- strkey verifies the checksum.
OWNER_SK = Keypair.random().secret
AUDITOR_SK = Keypair.random().secret
ADMIN_SK = Keypair.random().secret

DOC = {
    "skill_id": "com.acme.demo", "version": "1.0.0",
    "content_hash": "a" * 64, "verdict": "SAFE", "score": 88,
}
POISON = {**DOC, "skill_id": "com.evil.drainer", "verdict": "DANGEROUS", "score": 5}


@pytest.fixture
def cfg(tmp_path):
    return OrchestratorConfig(
        registry_id="C" + "A" * 55, tokens_id="C" + "B" * 55, escrow_id="C" + "C" * 55,
        owner_secret=OWNER_SK, auditor_secret=AUDITOR_SK, admin_secret=ADMIN_SK,
        reports_dir=tmp_path / "reports", journal_path=tmp_path / "journal.json",
    )


@pytest.fixture
def chain(monkeypatch):
    """Records every write the orchestrator attempts."""
    calls = []

    def tx(name, value=None):
        def _fn(*a, **k):
            calls.append(name)
            return onchain.TxResult(tx_hash=f"{name}-hash", value=value)
        return _fn

    monkeypatch.setattr(onchain, "lookup_by_hash", lambda *a, **k: None)
    monkeypatch.setattr(onchain, "get_version", lambda *a, **k: None)

    def simulate(cfg, contract_id, function, args=None):
        # get_request_count is 1 after our own create_audit_request landed;
        # is_verified_token is false so the mint path is exercised by default.
        return 1 if function == "get_request_count" else False

    monkeypatch.setattr(onchain, "simulate", simulate)
    monkeypatch.setattr(onchain, "register_skill", tx("register"))
    monkeypatch.setattr(onchain, "submit_verdict", tx("verdict"))
    monkeypatch.setattr(onchain, "mint_verified", tx("mint"))
    # The real contract returns the request_id; the orchestrator refuses to guess it.
    monkeypatch.setattr(onchain, "create_audit_request", tx("create", value=3))
    monkeypatch.setattr(onchain, "post_bond", tx("bond"))
    monkeypatch.setattr(onchain, "settle", tx("settle"))
    monkeypatch.setattr(onchain, "slash", tx("slash"))
    return calls


def test_safe_skill_registers_submits_and_mints(cfg, chain):
    result = orchestrator.orchestrate(DOC, cfg)
    assert chain == ["register", "verdict", "mint"]
    assert result.ok
    assert result.evidence_hash and len(result.evidence_hash) == 64


def test_dangerous_skill_is_never_minted(cfg, chain):
    """The claim the project rests on: only SAFE earns a badge."""
    result = orchestrator.orchestrate(POISON, cfg)
    assert "mint" not in chain
    mint = next(s for s in result.steps if s.step == Step.MINT)
    assert mint.status == "skipped"
    assert "DANGEROUS" in mint.detail


def test_already_registered_hash_skips_registration(cfg, chain, monkeypatch):
    """Idempotency comes from the hash index, not from the journal, so a re-run on a
    different machine behaves the same."""
    monkeypatch.setattr(onchain, "lookup_by_hash",
                        lambda *a, **k: {"skill_id": "com.acme.demo", "version": "1.0.0"})
    result = orchestrator.orchestrate(DOC, cfg)
    assert "register" not in chain
    assert next(s for s in result.steps if s.step == Step.REGISTER).status == "skipped"


def test_existing_badge_is_not_minted_twice(cfg, chain, monkeypatch):
    monkeypatch.setattr(onchain, "simulate", lambda *a, **k: True)  # badge exists
    result = orchestrator.orchestrate(DOC, cfg)
    assert "mint" not in chain
    assert next(s for s in result.steps if s.step == Step.MINT).status == "skipped"


def test_identical_verdict_is_not_resubmitted(cfg, chain, monkeypatch):
    """Found by the live e2e: the first run left register/mint idempotent but
    resubmitted the verdict every time."""
    from sterish_pipeline import reports

    doc_hash = reports.evidence_hash_of(DOC)
    monkeypatch.setattr(onchain, "get_version", lambda *a, **k: {
        "verdict": ["Safe"], "trust_score": 88, "evidence_hash": bytes.fromhex(doc_hash),
    })
    result = orchestrator.orchestrate(DOC, cfg)
    assert "verdict" not in chain
    assert next(s for s in result.steps if s.step == Step.VERDICT).status == "skipped"


def test_a_changed_score_is_still_submitted(cfg, chain, monkeypatch):
    """A differing score is a real update and must not be skipped."""
    from sterish_pipeline import reports

    monkeypatch.setattr(onchain, "get_version", lambda *a, **k: {
        "verdict": ["Safe"], "trust_score": 41,
        "evidence_hash": bytes.fromhex(reports.evidence_hash_of(DOC)),
    })
    orchestrator.orchestrate(DOC, cfg)
    assert "verdict" in chain


def test_evidence_hash_is_the_hash_of_the_published_report(cfg, chain):
    from sterish_pipeline import reports

    result = orchestrator.orchestrate(DOC, cfg)
    path = cfg.reports_dir / DOC["skill_id"] / f"{DOC['version']}.json"
    assert path.exists()
    assert reports.verify(path, result.evidence_hash) is True


def test_escrow_runs_only_when_asked(cfg, chain):
    orchestrate = orchestrator.orchestrate
    orchestrate(DOC, cfg)
    assert "create" not in chain

    cfg.run_escrow = True
    chain.clear()
    orchestrate(DOC, cfg)
    assert chain[-3:] == ["create", "bond", "settle"]


def test_dangerous_verdict_slashes_instead_of_settling(cfg, chain):
    cfg.run_escrow = True
    orchestrator.orchestrate(POISON, cfg)
    assert "slash" in chain and "settle" not in chain


def test_bonding_is_refused_when_the_request_id_is_unknown(cfg, chain, monkeypatch):
    """Found by the live e2e: the meta is v4, so reading only v3 lost the return
    value and the old `count - 1` fallback bonded against another party's request."""
    monkeypatch.setattr(onchain, "create_audit_request",
                        lambda *a, **k: onchain.TxResult(tx_hash="create-hash", value=None))
    cfg.run_escrow = True
    result = orchestrator.orchestrate(DOC, cfg)
    assert "bond" not in chain and "settle" not in chain
    bond = next(s for s in result.steps if s.step == Step.POST_BOND)
    assert bond.status == "failed" and "request_id" in bond.detail


def test_a_timeout_is_journalled_as_unknown_and_blocks_a_rerun(cfg, chain, monkeypatch):
    """Resubmitting a transaction that may have landed is worse than stopping."""
    def timeout(*a, **k):
        raise onchain.OnChainError("submit_verdict (abc) did not finalise within 60s")

    monkeypatch.setattr(onchain, "submit_verdict", timeout)
    with pytest.raises(onchain.OnChainError, match="did not finalise"):
        orchestrator.orchestrate(DOC, cfg)

    journal = Journal(cfg.journal_path)
    assert journal.has_unknown(DOC["skill_id"], DOC["version"]) == Step.VERDICT

    # A second run refuses to touch the chain again.
    monkeypatch.setattr(onchain, "submit_verdict", lambda *a, **k: onchain.TxResult("x"))
    with pytest.raises(onchain.OnChainError, match="UNKNOWN state"):
        orchestrator.orchestrate(DOC, cfg)


def test_contract_errors_propagate_untranslated(cfg, chain, monkeypatch):
    def refuse(*a, **k):
        raise onchain.ContractCallError(6, "register_skill")

    monkeypatch.setattr(onchain, "register_skill", refuse)
    with pytest.raises(onchain.ContractCallError) as exc:
        orchestrator.orchestrate(DOC, cfg)
    assert exc.value.code == 6 and "HashAlreadyRegistered" in str(exc.value)


def test_a_corrupt_journal_does_not_block_a_run(cfg, chain):
    cfg.journal_path.write_text("{ not json")
    assert orchestrator.orchestrate(DOC, cfg).ok


def test_dry_run_touches_nothing(cfg, chain):
    result = orchestrator.orchestrate(DOC, cfg, dry_run=True)
    assert chain == []
    assert result.steps == []


def test_a_completed_escrow_job_is_not_reopened(cfg, chain):
    """Re-opening a job would lock another fee and bond. Found by the live e2e."""
    cfg.run_escrow = True
    orchestrator.orchestrate(DOC, cfg)
    assert chain.count("create") == 1

    chain.clear()
    orchestrator.orchestrate(DOC, cfg)
    # The registry steps still run here because the stubbed chain reports no state;
    # what matters is that no second escrow job is opened.
    assert "create" not in chain and "bond" not in chain and "settle" not in chain
