"""Publish an audit report and derive its on-chain evidence hash.

The registry stores an ``evidence_hash`` alongside each verdict. For that hash
to be checkable, it must be the SHA-256 of *exactly the bytes a third party can
fetch* at ``report_uri`` — not of some internal summary string. This module is
the single place that turns an ``AuditReport`` into those canonical bytes and
their digest, so the value submitted on-chain and the value a reviewer computes
from the published file are the same by construction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sterish_pipeline.models import AuditReport


def canonical_report_bytes(report: AuditReport) -> bytes:
    """Serialize a report to stable, reproducible bytes.

    Sorted keys and a fixed separator make the output independent of field
    order, and a trailing newline makes it a well-formed text file. Two people
    serializing the same report get identical bytes, hence identical hashes.
    """
    payload = report.model_dump(mode="json")
    # The evidence hash must not depend on itself.
    payload.pop("evidence_hash", None)
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def evidence_hash_for(report: AuditReport) -> str:
    """The SHA-256 (64 lowercase hex) of the report's published bytes."""
    return hashlib.sha256(canonical_report_bytes(report)).hexdigest()


def publish_report(
    report: AuditReport,
    report_dir: Path | str,
    base_uri: str = "",
) -> tuple[Path, str, str]:
    """Write the report to disk and return (path, report_uri, evidence_hash).

    The written bytes are exactly the bytes the evidence hash is taken over, so
    ``sha256(published file) == evidence_hash`` holds for anyone who fetches it.
    """
    data = canonical_report_bytes(report)
    digest = hashlib.sha256(data).hexdigest()

    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{report.skill_id}@{report.version or 'unversioned'}.json"
    path = directory / filename
    path.write_bytes(data)

    report_uri = f"{base_uri.rstrip('/')}/{filename}" if base_uri else path.as_uri()
    return path, report_uri, digest


def verify_published_report(path: Path | str, expected_hash: str) -> bool:
    """Check that a published report file still hashes to the on-chain value."""
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest() == expected_hash
