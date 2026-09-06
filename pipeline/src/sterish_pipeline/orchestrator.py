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
from sterish_pipeline.models import FinalVerdict

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
        return {"step": str(self.step), "status": self.status,
                "tx_hash": self.tx_hash, "detail": self.detail}


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
        result.steps.extend(_run_escrow(journal, cfg, config, skill_id, version, verdict))

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

    if verdict == FinalVerdict.SAFE.value:
        steps.append(_run_step(
            journal, skill_id, version, Step.SETTLE,
            lambda: onchain.settle(cfg, config.escrow_id, config.admin_secret, request_id),
        ))
    else:
        # A bad audit forfeits the bond. With no external reporter the admin is paid,
        # which is the documented fallback in contracts/escrow (claim_forfeited).
        steps.append(_run_step(
            journal, skill_id, version, Step.SLASH,
            lambda: onchain.slash(cfg, config.escrow_id, config.admin_secret,
                                  request_id, config.admin_address),
        ))

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
