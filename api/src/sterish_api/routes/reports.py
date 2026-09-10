"""`GET /reports/{skill_id}/{version}` — the report `evidence_hash` commits to (STE-32).

`evidence_hash` is the only part of an audit that lives on the ledger. Everything a human
would actually read — the findings, the capability list, the recommendation — is off-chain
and anchored by that one hash (`specs/verdict-json.md` §6). Until this endpoint existed the
anchor pointed at nothing a caller could fetch, so `check` could say DANGEROUS but never
*why*, and the verification chain the whole design rests on was broken at its last link.

Two rules follow from that, and they are the reason this is not just a static file server:

* **The bytes are served exactly as they were hashed.** Not re-serialised, not re-ordered,
  not pretty-printed on the way out. Round-tripping the document through a JSON encoder
  makes the hash depend on separator and key-order choices, which is precisely how this
  kind of check quietly stops matching.
* **A mismatch is an error, never a 200.** If what is on disk does not hash to what the
  chain recorded, one of the two has been changed since the audit. Serving it anyway with a
  reassuring status code would hand a caller tampered evidence under our signature.
"""

import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, Response

from .. import chain
from ..config import settings
from ..errors import ApiError

logger = logging.getLogger(__name__)

router = APIRouter()

# Sync `def`: reading the file is blocking IO and the chain lookup is a Soroban
# simulation. See the note in routes/use.py.


def report_path(skill_id: str, version: str) -> Path | None:
    """Where `pipeline/reports.publish` writes: `<reports_dir>/<skill_id>/<version>.json`.

    Returns None when reports are not configured or the file is absent, so the caller
    decides between "not configured" and "no report for this version" — they are
    different answers and a client can act on the difference.

    `skill_id` and `version` come straight off the URL, so the resolved path is checked
    to be inside the reports directory. A `skill_id` of `../../etc` would otherwise be a
    file read primitive, and FastAPI does not decode away every traversal for us.
    """
    if not settings.reports_dir:
        return None

    root = Path(settings.reports_dir).resolve()
    candidate = (root / skill_id / f"{version}.json").resolve()
    if not candidate.is_relative_to(root):
        raise ApiError(400, "INVALID_PARAMETER", "skill_id and version must not traverse paths")
    return candidate if candidate.is_file() else None


@router.get("/reports/{skill_id}/{version}")
def get_report(skill_id: str, version: str):
    """Serve the verdict document, having first checked it against the ledger."""
    if not skill_id or not version:
        raise ApiError(400, "INVALID_PARAMETER", "skill_id and version must be non-empty")

    if not settings.reports_dir:
        raise ApiError(503, "NOT_CONFIGURED", "STERISH_REPORTS_DIR is not set")

    path = report_path(skill_id, version)
    if path is None:
        # Explicitly not an empty object: a caller must be able to tell "no report" from
        # "a report saying nothing was found".
        raise ApiError(
            404,
            "REPORT_NOT_FOUND",
            f"no published report for {skill_id}@{version}",
            {"skill_id": skill_id, "version": version},
        )

    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()

    record = chain.get_version(skill_id, version)
    expected = record["evidence_hash"]

    if not expected:
        # The version is registered but carries no anchor, so there is nothing to check
        # the bytes against. Serving them would imply a verification that did not happen.
        raise ApiError(
            409,
            "NO_EVIDENCE_ANCHOR",
            f"{skill_id}@{version} has no evidence_hash on chain to verify this report against",
            {"report_sha256": digest},
        )

    if digest != expected:
        logger.error(
            "report hash mismatch for %s@%s: disk %s, chain %s",
            skill_id, version, digest, expected,
        )
        raise ApiError(
            500,
            "REPORT_HASH_MISMATCH",
            "published report does not match the evidence_hash recorded on chain",
            {"report_sha256": digest, "evidence_hash": expected},
        )

    return Response(
        content=payload,
        media_type="application/json",
        headers={
            # So a client can check our arithmetic without re-reading the chain itself.
            "X-STERISH-EVIDENCE-HASH": expected,
            "Cache-Control": "public, max-age=300",
        },
    )
