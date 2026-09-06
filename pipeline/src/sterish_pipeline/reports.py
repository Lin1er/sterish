"""Publish the audit report that `evidence_hash` on-chain commits to.

`evidence_hash` is the only part of an audit that lives on the ledger. The report
itself is off-chain and mutable, so the contract between them has to be exact: the
bytes served at `report_uri` must hash to the `evidence_hash` that was submitted,
and a third party must be able to recompute it without trusting us.

Hence one rule: the bytes are written to disk and hashed *once*, and the same bytes
are what get published. Re-serialising the document before hashing would make the
hash depend on dict ordering and separator choices, which is how this kind of check
quietly stops matching.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PublishedReport:
    path: Path
    evidence_hash: str
    size: int

    def uri(self, base_url: str = "") -> str:
        """Public URL for the report, or a file:// URI when no base is configured."""
        if not base_url:
            return self.path.resolve().as_uri()
        return f"{base_url.rstrip('/')}/{self.path.name}"


def canonical_bytes(document: dict) -> bytes:
    """The exact bytes that get published and hashed.

    `sort_keys` plus a trailing newline: stable across runs and across machines, and
    the file still reads as normal JSON to anyone who opens it.
    """
    text = json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False)
    return text.encode("utf-8") + b"\n"


def evidence_hash_of(document: dict) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def publish(
    document: dict, skill_id: str, version: str, reports_dir: Path | str
) -> PublishedReport:
    """Write the verdict document and return the hash of exactly what was written."""
    payload = canonical_bytes(document)
    directory = Path(reports_dir) / skill_id
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / f"{version}.json"
    path.write_bytes(payload)

    return PublishedReport(
        path=path,
        evidence_hash=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
    )


def verify(path: Path | str, expected_hash: str) -> bool:
    """Recompute the hash of a published report — what a third party runs."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected_hash
