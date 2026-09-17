"""Land an audit on chain: register -> submit_verdict -> mint/settle or slash.

Without this the pipeline's verdicts are local JSON files and the project's central
claim -- an unforgeable on-chain verdict -- is unproven.

## Why there is a journal

The flow spans several transactions that cannot be made atomic across contracts. A
crash between `submit_verdict` and `mint_verified` leaves a version audited but
unbadged, and a blind re-run would try to register an already-registered hash. So
each completed step is journalled with its transaction hash, and a resumed run
skips what the ledger already shows. Two independent safeguards:

  * every step re-reads chain state before acting (`lookup_by_hash`, `is_verified`),
    so the journal is an optimisation, not the source of truth;
  * a step whose outcome is genuinely UNKNOWN (submitted but not confirmed in time)
    is recorded as such and blocks an automatic re-run, because resubmitting a
    transaction that may have landed is worse than stopping.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from stellar_sdk import Keypair

from sterish_pipeline import onchain, reports
from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import FinalVerdict, Verdict

logger = logging.getLogger(__name__)


class Step(StrEnum):
    REGISTER = "register_skill"
    PUBLISH = "publish_report"
    VERDICT = "submit_verdict"
    MINT = "mint_verified"
    CREATE_REQUEST = "create_audit_request"
    POST_BOND = "post_bond"
    SETTLE = "settle"
    SLASH = "slash"


@dataclass
class OrchestratorConfig:
    """Addresses and signers. Secrets come from the environment, never from a file
    that could be committed."""

    registry_id: str
    tokens_id: str = ""
    escrow_id: str = ""
    owner_secret: str = ""      # registers skills
    auditor_secret: str = ""    # submits verdicts, mints badges
    admin_secret: str = ""      # settles and slashes escrow
    reports_dir: Path = Path("reports")
    report_base_url: str = ""
    journal_path: Path = Path(".sterish-journal.json")
    network: str = "testnet"
    # Escrow amounts are in stroops (1 USDC = 10_000_000).
    fee_amount: int = 50_000_000
    bond_amount: int = 100_000_000
    run_escrow: bool = False
    # When the escrow job is opened (STE-49):
    #   "after_verdict" — the original order: register, verdict, then create + bond +
    #                     settle/slash in one go. Kept as the default so existing runs
    #                     do not change underneath anyone.
    #   "before_audit"  — the product order: `open_escrow_job` locks fee + bond BEFORE the
    #                     audit runs, and `orchestrate` then closes that same job, found
    #                     by the request_id the journal recorded. Never guessed.
    escrow_lock: str = "after_verdict"
    # Who a slashed bond goes to. Empty = the admin, and the step says so explicitly.
    #
    # That fallback is an operational convenience for our own runs (seed, rehearsal), NOT
    # product behaviour: in a real report-and-slash flow there is always a reporter, and if
    # there is none, nobody reported anything and the slash path should not have been
    # reached. Callers running the product flow should always set this.
    reporter_address: str = ""

    @property
    def owner_address(self) -> str:
        return Keypair.from_secret(self.owner_secret).public_key

    @property
    def auditor_address(self) -> str:
        return Keypair.from_secret(self.auditor_secret).public_key

    @property
    def admin_address(self) -> str:
        return Keypair.from_secret(self.admin_secret).public_key


@dataclass
class StepResult:
    step: Step
    status: str                 # done | skipped | unknown | failed
    tx_hash: str | None = None
    detail: str = ""
    # Contract return value, when the transaction meta carried one (e.g. the
    # request_id from create_audit_request).
    value: Any = None

    @property
    def tx_url(self) -> str | None:
        return None if not self.tx_hash else f"https://stellar.expert/explorer/testnet/tx/{self.tx_hash}"

    def to_dict(self) -> dict:
        out = {"step": str(self.step), "status": self.status,
               "tx_hash": self.tx_hash, "detail": self.detail}
        # The escrow request_id is the one value a later run must read back from the
        # journal (STE-49: the job is opened before the audit and closed after it).
        if self.step == Step.CREATE_REQUEST and isinstance(self.value, int):
            out["request_id"] = self.value
        return out


@dataclass
class OrchestrationResult:
    skill_id: str
    version: str
    content_hash: str
    verdict: str
    score: int
    evidence_hash: str = ""
    report_uri: str = ""
    steps: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(s.status in ("failed", "unknown") for s in self.steps)

    def tx_hashes(self) -> dict[str, str]:
        return {str(s.step): s.tx_hash for s in self.steps if s.tx_hash}

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id, "version": self.version,
            "content_hash": self.content_hash, "verdict": self.verdict,
            "score": self.score, "evidence_hash": self.evidence_hash,
            "report_uri": self.report_uri, "ok": self.ok,
            "steps": [s.to_dict() for s in self.steps],
        }


class Journal:
    """Append-only record of completed steps, keyed by (skill_id, version)."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._data: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                # A corrupt journal must not block a run: chain state is authoritative.
                logger.warning("journal unreadable (%s); starting a fresh one", exc)
                self._data = {}

    @staticmethod
    def _key(skill_id: str, version: str) -> str:
        return f"{skill_id}@{version}"

    def get(self, skill_id: str, version: str, step: Step) -> dict | None:
        return self._data.get(self._key(skill_id, version), {}).get(str(step))

    def record(self, skill_id: str, version: str, result: StepResult) -> None:
        self._data.setdefault(self._key(skill_id, version), {})[str(result.step)] = result.to_dict()
        try:
            self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))
        except OSError as exc:
            logger.warning("could not persist journal: %s", exc)

    def has_unknown(self, skill_id: str, version: str) -> Step | None:
        for name, entry in self._data.get(self._key(skill_id, version), {}).items():
            if entry.get("status") == "unknown":
                return Step(name)
        return None


def _run_step(journal: Journal, skill_id: str, version: str, step: Step, action) -> StepResult:
    """Execute one step, translating an unconfirmed submission into `unknown`."""
    try:
        tx = action()
    except onchain.ContractCallError:
        # A typed contract error is a decision, not a transport fault: let it out
        # unjournalled so the caller sees exactly which invariant refused.
        raise
    except onchain.OnChainError as exc:
        # A timeout means the transaction may still land. Recording it as failed would
        # invite a re-run that double-applies it.
        status = "unknown" if "did not finalise" in str(exc) else "failed"
        result = StepResult(step, status, None, str(exc))
        journal.record(skill_id, version, result)
        raise
    result = StepResult(step, "done", tx.tx_hash if tx else None,
                        value=tx.value if tx else None)
    journal.record(skill_id, version, result)
    return result


def orchestrate(
    document: dict,
    config: OrchestratorConfig,
    pipeline_config: PipelineConfig | None = None,
    *,
    dry_run: bool = False,
) -> OrchestrationResult:
    """Land one audited skill version on chain.

    `document` is the frozen verdict document (`specs/verdict-json.md`).
    """
    cfg = pipeline_config or PipelineConfig()
    skill_id = document["skill_id"]
    version = document["version"]
    content_hash = document["content_hash"]
    verdict = document["verdict"]
    score = int(document["score"])

    result = OrchestrationResult(
        skill_id=skill_id, version=version, content_hash=content_hash,
        verdict=verdict, score=score,
    )
    journal = Journal(config.journal_path)

    stuck = journal.has_unknown(skill_id, version)
    if stuck:
        raise onchain.OnChainError(
            f"previous run left {stuck} in an UNKNOWN state for {skill_id}@{version}. "
            "Check the ledger and clear that entry from the journal before re-running."
        )

    if dry_run:
        logger.info("dry run: would orchestrate %s@%s -> %s", skill_id, version, verdict)
        return result

    # 1. Register, unless these exact bytes are already pinned. Asking the hash index
    #    rather than the journal makes the run idempotent across machines.
    existing = onchain.lookup_by_hash(cfg, config.registry_id, content_hash)
    if existing is not None:
        pinned = f"{existing.get('skill_id')}@{existing.get('version')}"
        result.steps.append(StepResult(
            Step.REGISTER, "skipped", None, f"content_hash already registered as {pinned}",
        ))
    else:
        result.steps.append(_run_step(
            journal, skill_id, version, Step.REGISTER,
            lambda: onchain.register_skill(
                cfg, config.registry_id, config.owner_secret, skill_id, version, content_hash),
        ))

    # 2. Publish the report, then submit the hash of exactly those bytes.
    published = reports.publish(document, skill_id, version, config.reports_dir)
    result.evidence_hash = published.evidence_hash
    result.report_uri = published.uri(config.report_base_url)
    result.steps.append(StepResult(
        Step.PUBLISH, "done", None, f"{published.path} ({published.size} bytes)"))

    if _verdict_already_on_chain(cfg, config, skill_id, version, verdict, score,
                                 published.evidence_hash):
        # Re-running must not resubmit an identical verdict: it costs a fee for no
        # state change, and if the verdict ever differed the contract would emit a
        # verdict_flipped that never actually flipped anything.
        result.steps.append(StepResult(
            Step.VERDICT, "skipped", None, "identical verdict already recorded on chain"))
    else:
        result.steps.append(_run_step(
            journal, skill_id, version, Step.VERDICT,
            lambda: onchain.submit_verdict(
                cfg, config.registry_id, config.auditor_secret,
                skill_id, version, verdict, score, published.evidence_hash),
        ))

    # 3. Only SAFE earns a badge. The contract enforces this too (mint_verified checks
    #    registry.is_verified), so this is defence in depth, not the only gate.
    if verdict == FinalVerdict.SAFE.value and config.tokens_id:
        if onchain.simulate(cfg, config.tokens_id, "is_verified_token",
                            [onchain.scval.to_string(skill_id), onchain.scval.to_string(version)]):
            result.steps.append(StepResult(Step.MINT, "skipped", None, "badge already minted"))
        else:
            result.steps.append(_run_step(
                journal, skill_id, version, Step.MINT,
                lambda: onchain.mint_verified(
                    cfg, config.tokens_id, config.auditor_secret,
                    skill_id, version, config.owner_address),
            ))
    elif verdict != FinalVerdict.SAFE.value:
        result.steps.append(StepResult(
            Step.MINT, "skipped", None, f"verdict is {verdict}, not SAFE — no badge"))

    # 4. Economic path, opt-in: it moves real balances and needs a funded escrow.
    if config.run_escrow and config.escrow_id:
        _check_escrow_config(config)
        if config.escrow_lock == "before_audit":
            result.steps.extend(_close_escrow_job(journal, cfg, config, skill_id, version, verdict))
        else:
            result.steps.extend(_run_escrow(journal, cfg, config, skill_id, version, verdict))

    return result


ESCROW_LOCK_MODES = ("after_verdict", "before_audit")


def _check_escrow_config(config: OrchestratorConfig) -> None:
    if config.escrow_lock not in ESCROW_LOCK_MODES:
        raise ValueError(
            f"escrow_lock must be one of {ESCROW_LOCK_MODES}, got {config.escrow_lock!r}"
        )
    if config.reporter_address and not onchain.is_account_address(config.reporter_address):
        raise ValueError(
            f"reporter_address must be a Stellar account (G...), got {config.reporter_address!r}"
        )


def open_escrow_job(
    skill_id: str,
    version: str,
    config: OrchestratorConfig,
    pipeline_config: PipelineConfig | None = None,
) -> list[StepResult]:
    """Lock the developer's fee and the auditor's bond BEFORE the audit runs (STE-49).

    `create_audit_request` then `post_bond`. The request_id the contract returns is
    journalled with the step, so the `orchestrate` call that follows the audit closes
    exactly this job. Re-running resumes: a job already created is not created again,
    a bond already posted is not posted again.
    """
    _check_escrow_config(config)
    cfg = pipeline_config or PipelineConfig()
    journal = Journal(config.journal_path)
    stuck = journal.has_unknown(skill_id, version)
    if stuck:
        raise onchain.OnChainError(
            f"previous run left {stuck} in an UNKNOWN state for {skill_id}@{version}. "
            "Check the ledger and clear that entry from the journal before re-running."
        )
    if not config.escrow_id:
        raise ValueError("open_escrow_job needs escrow_id")

    steps: list[StepResult] = []
    created = journal.get(skill_id, version, Step.CREATE_REQUEST)
    closed = journal.get(skill_id, version, Step.SETTLE) or journal.get(
        skill_id, version, Step.SLASH
    )
    if created and created.get("status") == "done" and not (
        closed and closed.get("status") == "done"
    ):
        request_id = created.get("request_id")
        steps.append(StepResult(
            Step.CREATE_REQUEST, "skipped", created.get("tx_hash"),
            f"escrow job #{request_id} already open for this version (journal)",
            value=request_id,
        ))
    elif created and created.get("status") == "done":
        # A finished job exists; opening another is a deliberate act, not a resume.
        steps.append(StepResult(
            Step.CREATE_REQUEST, "skipped", created.get("tx_hash"),
            "escrow job already run to completion for this version (journal); "
            "delete the journal entry to open another",
        ))
        return steps
    else:
        result = _run_step(
            journal, skill_id, version, Step.CREATE_REQUEST,
            lambda: onchain.create_audit_request(
                cfg, config.escrow_id, config.owner_secret, skill_id, version,
                config.fee_amount, config.bond_amount),
        )
        steps.append(result)
        request_id = _request_id_from(cfg, config, result)

    if not isinstance(request_id, int):
        steps.append(StepResult(Step.POST_BOND, "failed", None, "could not resolve request_id"))
        return steps

    bonded = journal.get(skill_id, version, Step.POST_BOND)
    if bonded and bonded.get("status") == "done":
        steps.append(StepResult(Step.POST_BOND, "skipped", bonded.get("tx_hash"),
                                f"bond already posted on #{request_id} (journal)"))
    else:
        steps.append(_run_step(
            journal, skill_id, version, Step.POST_BOND,
            lambda: onchain.post_bond(cfg, config.escrow_id, config.auditor_secret, request_id),
        ))
    return steps


def _close_escrow_job(journal, cfg, config, skill_id, version, verdict) -> list[StepResult]:
    """Settle or slash the job `open_escrow_job` locked, found through the journal."""
    _check_escrow_config(config)
    for step in (Step.SETTLE, Step.SLASH):
        done = journal.get(skill_id, version, step)
        if done and done.get("status") == "done":
            return [StepResult(step, "skipped", done.get("tx_hash"),
                               "escrow job already closed for this version (journal)")]

    created = journal.get(skill_id, version, Step.CREATE_REQUEST)
    bonded = journal.get(skill_id, version, Step.POST_BOND)
    request_id = (created or {}).get("request_id")
    if not isinstance(request_id, int) or not (bonded and bonded.get("status") == "done"):
        step = Step.SETTLE if verdict == FinalVerdict.SAFE.value else Step.SLASH
        return [StepResult(
            step, "failed", None,
            "escrow_lock=before_audit but the journal holds no bonded job for this version; "
            "run open_escrow_job before the audit (nothing was settled or slashed)",
        )]

    # The journal is local and could be stale or copied from elsewhere. Before moving
    # money, confirm on chain that this request is ours and still Bonded.
    record = onchain.simulate(cfg, config.escrow_id, "get_request",
                              [onchain.scval.to_uint32(request_id)])
    status = record.get("status") if isinstance(record, dict) else None
    if isinstance(status, (list, tuple)) and status:
        status = status[0]
    if not isinstance(record, dict) or record.get("skill_id") != skill_id or record.get(
        "version"
    ) != version or str(status) != "Bonded":
        step = Step.SETTLE if verdict == FinalVerdict.SAFE.value else Step.SLASH
        seen = (f"{record.get('skill_id')}@{record.get('version')} {status}"
                if isinstance(record, dict) else repr(record))
        return [StepResult(
            step, "failed", None,
            f"journal says request #{request_id}, but on chain it is {seen}, not a Bonded "
            f"job for {skill_id}@{version}; refusing to settle or slash it",
        )]

    return [_settle_or_slash(journal, cfg, config, skill_id, version, verdict, request_id)]


def _settle_or_slash(journal, cfg, config, skill_id, version, verdict, request_id) -> StepResult:
    if verdict == FinalVerdict.SAFE.value:
        return _run_step(
            journal, skill_id, version, Step.SETTLE,
            lambda: onchain.settle(cfg, config.escrow_id, config.admin_secret, request_id),
        )
    reporter = config.reporter_address or config.admin_address
    result = _run_step(
        journal, skill_id, version, Step.SLASH,
        lambda: onchain.slash(cfg, config.escrow_id, config.admin_secret, request_id, reporter),
    )
    result.detail = (
        f"bond forfeited to reporter {reporter}" if config.reporter_address
        else f"no reporter given: bond forfeited to the admin {reporter} (explicit fallback)"
    )
    return result


def register_only(
    skill_id: str,
    version: str,
    content_hash: str,
    config: OrchestratorConfig,
    pipeline_config: PipelineConfig | None = None,
) -> OrchestrationResult:
    """Register a version and stop. No report, no verdict, no badge.

    This is how an **UNAUDITED** record is produced, and the only way: the contract
    refuses `AuditVerdict::Unaudited` in `submit_verdict` (registry error #9), so a
    version is unaudited exactly when nobody has submitted a verdict for it yet.

    It exists for the demo data the dashboard needs: a skill whose *latest* version
    has not been audited is the case that makes `latest_version` and
    `latest_audited_version` differ, which is the stale-version warning at
    api-spec 3.3. Faking that state in a fixture would prove nothing — the warning
    has to fire on what the chain actually holds.
    """
    cfg = pipeline_config or PipelineConfig()
    result = OrchestrationResult(
        skill_id=skill_id, version=version, content_hash=content_hash,
        verdict=Verdict.UNAUDITED.value,
        score=0,
    )
    journal = Journal(config.journal_path)

    stuck = journal.has_unknown(skill_id, version)
    if stuck:
        raise onchain.OnChainError(
            f"previous run left {stuck} in an UNKNOWN state for {skill_id}@{version}. "
            "Check the ledger and clear that entry from the journal before re-running."
        )

    existing = onchain.lookup_by_hash(cfg, config.registry_id, content_hash)
    if existing is not None:
        pinned = f"{existing.get('skill_id')}@{existing.get('version')}"
        result.steps.append(StepResult(
            Step.REGISTER, "skipped", None, f"content_hash already registered as {pinned}",
        ))
    else:
        result.steps.append(_run_step(
            journal, skill_id, version, Step.REGISTER,
            lambda: onchain.register_skill(
                cfg, config.registry_id, config.owner_secret, skill_id, version, content_hash),
        ))

    result.steps.append(StepResult(
        Step.VERDICT, "skipped", None,
        "register-only: no verdict submitted, the version stays UNAUDITED"))
    result.steps.append(StepResult(
        Step.MINT, "skipped", None, "verdict is UNAUDITED, not SAFE — no badge"))
    return result


def _run_escrow(journal, cfg, config, skill_id, version, verdict) -> list[StepResult]:
    """create_audit_request -> post_bond -> settle (SAFE) or slash (not SAFE).

    Unlike the registry steps, this moves balances, and the escrow has no notion of
    "already done for this version" — a second run would open a second job and lock
    another fee and bond. So a completed job is skipped based on the journal.

    That guard is local to the journal file, deliberately: the chain cannot tell us
    which request belongs to which audit run, so there is no on-chain equivalent of
    the `lookup_by_hash` check used for registration. Running from a fresh machine
    with no journal will open a new job.
    """
    steps: list[StepResult] = []

    previous = journal.get(skill_id, version, Step.CREATE_REQUEST)
    if previous and previous.get("status") == "done":
        return [StepResult(
            Step.CREATE_REQUEST, "skipped", previous.get("tx_hash"),
            "escrow job already run for this version (journal); "
            "delete the journal entry to open another",
        )]

    created = _run_step(
        journal, skill_id, version, Step.CREATE_REQUEST,
        lambda: onchain.create_audit_request(
            cfg, config.escrow_id, config.owner_secret, skill_id, version,
            config.fee_amount, config.bond_amount),
    )
    steps.append(created)

    request_id = _request_id_from(cfg, config, created)
    if request_id is None:
        steps.append(StepResult(Step.POST_BOND, "failed", None, "could not resolve request_id"))
        return steps

    steps.append(_run_step(
        journal, skill_id, version, Step.POST_BOND,
        lambda: onchain.post_bond(cfg, config.escrow_id, config.auditor_secret, request_id),
    ))

    # A bad audit forfeits the bond — to the reporter when one is configured (STE-49),
    # otherwise to the admin, the documented fallback in contracts/escrow, and the step
    # says which.
    steps.append(_settle_or_slash(journal, cfg, config, skill_id, version, verdict, request_id))
    return steps


def _verdict_already_on_chain(cfg, config, skill_id, version, verdict, score,
                              evidence_hash) -> bool:
    """True when the chain already holds exactly this verdict for this version.

    Compares all three fields: a differing score or evidence_hash is a real update
    and must still be submitted.
    """
    try:
        record = onchain.get_version(cfg, config.registry_id, skill_id, version)
    except onchain.ContractCallError:
        return False          # not registered or no such version yet
    if not isinstance(record, dict):
        return False

    on_chain_verdict = record.get("verdict")
    if isinstance(on_chain_verdict, (list, tuple)) and on_chain_verdict:
        on_chain_verdict = on_chain_verdict[0]
    stored_hash = record.get("evidence_hash")
    stored_hash = stored_hash.hex() if isinstance(stored_hash, (bytes, bytearray)) else stored_hash

    return (
        str(on_chain_verdict).upper() == str(verdict).upper()
        and int(record.get("trust_score") or 0) == int(score)
        and stored_hash == evidence_hash
    )


def _request_id_from(cfg, config, created: StepResult) -> int | None:
    """The request_id the contract returned, or None. There is deliberately no
    fallback -- see the comment below."""
    if isinstance(created.value, int):
        return created.value
    # No guessing. `get_request_count() - 1` looks reasonable and is wrong often
    # enough to matter: on the rehearsal escrow it resolved to a request created by
    # someone else, and post_bond would then have locked a bond against it. Refusing
    # is the only safe answer when the id is not known.
    logger.error(
        "create_audit_request returned no request_id in its transaction meta "
        "(tx %s); refusing to guess one", created.tx_hash,
    )
    return None
