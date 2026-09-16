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


class TestRegisterOnly:
    """`register_only` is how the UNAUDITED demo state is produced (STE-18)."""

    def test_registers_and_submits_nothing_else(self, cfg, chain):
        result = orchestrator.register_only("com.acme.demo", "2.0.0", "b" * 64, cfg)
        assert chain == ["register"]
        assert result.ok
        assert result.verdict == "UNAUDITED"
        assert result.score == 0

    def test_no_verdict_and_no_badge(self, cfg, chain):
        result = orchestrator.register_only("com.acme.demo", "2.0.0", "b" * 64, cfg)
        steps = {str(s.step): s for s in result.steps}
        assert steps["submit_verdict"].status == "skipped"
        assert steps["mint_verified"].status == "skipped"
        assert "UNAUDITED" in steps["submit_verdict"].detail

    def test_publishes_no_report(self, cfg, chain):
        """An unaudited version has no evidence, so it must not advertise any."""
        result = orchestrator.register_only("com.acme.demo", "2.0.0", "b" * 64, cfg)
        assert result.evidence_hash == ""
        assert result.report_uri == ""
        assert not (cfg.reports_dir / "com.acme.demo").exists()

    def test_already_registered_hash_is_skipped(self, cfg, chain, monkeypatch):
        monkeypatch.setattr(
            onchain, "lookup_by_hash",
            lambda *a, **k: {"skill_id": "com.acme.demo", "version": "2.0.0"},
        )
        result = orchestrator.register_only("com.acme.demo", "2.0.0", "b" * 64, cfg)
        assert chain == []
        assert next(s for s in result.steps if s.step == Step.REGISTER).status == "skipped"


# --- STE-49: lock before the audit, slash to the reporter ------------------------------

REPORTER = Keypair.random().public_key


@pytest.fixture
def escrow_chain(chain, monkeypatch):
    """The chain fixture, plus an escrow that remembers its requests and records who a
    slash paid, so a test can assert the arguments, not only the call order."""
    requests: dict[int, dict] = {}
    slashed_to: list[str] = []
    next_id = [7]

    def create(cfg, escrow_id, requestor_secret, skill_id, version, fee, bond):
        chain.append("create")
        rid = next_id[0]
        next_id[0] += 1
        requests[rid] = {"skill_id": skill_id, "version": version, "status": ["Open"]}
        return onchain.TxResult(tx_hash=f"create-{rid}", value=rid)

    def bond(cfg, escrow_id, auditor_secret, request_id):
        chain.append("bond")
        requests[request_id]["status"] = ["Bonded"]
        return onchain.TxResult(tx_hash=f"bond-{request_id}")

    def settle(cfg, escrow_id, admin_secret, request_id):
        chain.append(f"settle#{request_id}")
        requests[request_id]["status"] = ["Settled"]
        return onchain.TxResult(tx_hash=f"settle-{request_id}")

    def slash(cfg, escrow_id, admin_secret, request_id, reporter):
        chain.append(f"slash#{request_id}")
        slashed_to.append(reporter)
        requests[request_id]["status"] = ["Slashed"]
        return onchain.TxResult(tx_hash=f"slash-{request_id}")

    def simulate(cfg, contract_id, function, args=None):
        if function == "get_request":
            rid = int(onchain.scval.to_native(args[0]))
            return requests.get(rid)
        return False

    monkeypatch.setattr(onchain, "create_audit_request", create)
    monkeypatch.setattr(onchain, "post_bond", bond)
    monkeypatch.setattr(onchain, "settle", settle)
    monkeypatch.setattr(onchain, "slash", slash)
    monkeypatch.setattr(onchain, "simulate", simulate)
    return {"calls": chain, "requests": requests, "slashed_to": slashed_to}


@pytest.fixture
def before_audit(cfg):
    cfg.run_escrow = True
    cfg.escrow_lock = "before_audit"
    return cfg


class TestLockBeforeAudit:
    def test_fee_and_bond_are_locked_before_anything_else_happens(self, before_audit, escrow_chain):
        steps = orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        assert escrow_chain["calls"] == ["create", "bond"]
        assert [s.status for s in steps] == ["done", "done"]
        assert escrow_chain["requests"][7]["status"] == ["Bonded"]

    def test_the_audit_result_closes_the_same_job(self, before_audit, escrow_chain):
        orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        result = orchestrator.orchestrate(DOC, before_audit)
        assert escrow_chain["calls"] == [
            "create", "bond", "register", "verdict", "mint", "settle#7"
        ]
        assert result.ok

    def test_the_request_id_is_carried_by_the_journal_not_guessed(self, before_audit, escrow_chain):
        orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        # Another job opened by someone else in between must not be the one settled.
        escrow_chain["requests"][99] = {
            "skill_id": DOC["skill_id"], "version": DOC["version"], "status": ["Bonded"]
        }
        orchestrator.orchestrate(DOC, before_audit)
        assert "settle#7" in escrow_chain["calls"] and "settle#99" not in escrow_chain["calls"]
        entry = Journal(before_audit.journal_path).get(DOC["skill_id"], DOC["version"],
                                                       Step.CREATE_REQUEST)
        assert entry["request_id"] == 7

    def test_a_dangerous_verdict_slashes_the_locked_bond_to_the_reporter(
        self, before_audit, escrow_chain
    ):
        before_audit.reporter_address = REPORTER
        orchestrator.open_escrow_job(POISON["skill_id"], POISON["version"], before_audit)
        result = orchestrator.orchestrate(POISON, before_audit)
        assert escrow_chain["calls"][-1] == "slash#7"
        assert escrow_chain["slashed_to"] == [REPORTER]
        slash = next(s for s in result.steps if s.step == Step.SLASH)
        assert REPORTER in slash.detail and "reporter" in slash.detail

    def test_closing_without_an_open_job_moves_nothing(self, before_audit, escrow_chain):
        result = orchestrator.orchestrate(DOC, before_audit)
        settle = next(s for s in result.steps if s.step == Step.SETTLE)
        assert settle.status == "failed"
        assert "open_escrow_job" in settle.detail
        assert not any(c.startswith(("settle#", "slash#")) for c in escrow_chain["calls"])
        assert not result.ok

    @pytest.mark.parametrize(
        "tamper, why",
        [
            ({"skill_id": "com.someone.else"}, "someone else's request"),
            ({"version": "9.9.9"}, "another version"),
            ({"status": ["Settled"]}, "already settled"),
        ],
    )
    def test_a_journal_that_disagrees_with_the_chain_is_refused(
        self, before_audit, escrow_chain, tamper, why
    ):
        orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        escrow_chain["requests"][7].update(tamper)
        result = orchestrator.orchestrate(DOC, before_audit)
        settle = next(s for s in result.steps if s.step == Step.SETTLE)
        assert settle.status == "failed", why
        assert "refusing" in settle.detail
        assert "settle#7" not in escrow_chain["calls"]

    def test_opening_again_resumes_instead_of_locking_twice(self, before_audit, escrow_chain):
        orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        steps = orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        assert escrow_chain["calls"] == ["create", "bond"]
        assert [s.status for s in steps] == ["skipped", "skipped"]

    def test_a_crash_between_create_and_bond_resumes_at_the_bond(
        self, before_audit, escrow_chain, monkeypatch
    ):
        def bond_times_out(*a, **k):
            raise onchain.OnChainError("rpc refused the connection")

        real_bond = onchain.post_bond
        monkeypatch.setattr(onchain, "post_bond", bond_times_out)
        with pytest.raises(onchain.OnChainError):
            orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        monkeypatch.setattr(onchain, "post_bond", real_bond)
        orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        assert escrow_chain["calls"] == ["create", "bond"]  # one job, one bond

    def test_a_closed_job_is_not_closed_twice_or_reopened(self, before_audit, escrow_chain):
        orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        orchestrator.orchestrate(DOC, before_audit)
        orchestrator.orchestrate(DOC, before_audit)
        steps = orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        assert escrow_chain["calls"].count("settle#7") == 1
        assert escrow_chain["calls"].count("create") == 1
        assert "completion" in steps[0].detail

    def test_the_request_id_is_never_guessed_when_the_contract_returns_none(
        self, before_audit, escrow_chain, monkeypatch
    ):
        monkeypatch.setattr(onchain, "create_audit_request",
                            lambda *a, **k: onchain.TxResult(tx_hash="c", value=None))
        steps = orchestrator.open_escrow_job(DOC["skill_id"], DOC["version"], before_audit)
        assert steps[-1].step == Step.POST_BOND and steps[-1].status == "failed"
        assert "bond" not in escrow_chain["calls"]


class TestReporter:
    def test_after_verdict_mode_also_pays_the_reporter(self, cfg, escrow_chain):
        cfg.run_escrow = True
        cfg.reporter_address = REPORTER
        orchestrator.orchestrate(POISON, cfg)
        assert escrow_chain["slashed_to"] == [REPORTER]

    def test_no_reporter_falls_back_to_the_admin_and_says_so(self, cfg, escrow_chain):
        cfg.run_escrow = True
        result = orchestrator.orchestrate(POISON, cfg)
        assert escrow_chain["slashed_to"] == [cfg.admin_address]
        slash = next(s for s in result.steps if s.step == Step.SLASH)
        assert "explicit fallback" in slash.detail

    @pytest.mark.parametrize(
        "bad",
        ["not-an-address", "CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE"],
    )
    def test_an_invalid_reporter_is_refused_before_any_money_moves(self, cfg, escrow_chain, bad):
        cfg.run_escrow = True
        cfg.reporter_address = bad
        with pytest.raises(ValueError, match="reporter_address"):
            orchestrator.orchestrate(POISON, cfg)
        assert not any(c.startswith(("create", "slash#")) for c in escrow_chain["calls"])

    def test_an_unknown_lock_mode_is_refused(self, cfg, escrow_chain):
        cfg.run_escrow = True
        cfg.escrow_lock = "whenever"
        with pytest.raises(ValueError, match="escrow_lock"):
            orchestrator.orchestrate(DOC, cfg)
