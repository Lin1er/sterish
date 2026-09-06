"""The audit corpus: snapshot bytes on disk plus a provenance index.

Skills are snapshotted into the repo rather than fetched at audit time. Fetching
live would mean the `content_hash` drifts whenever upstream edits a paragraph,
and an audit whose subject can change under it proves nothing. A snapshot with a
recorded source URL, fetch timestamp, and upstream digest is reproducible: a
third party clones the repo and recomputes every hash from the bytes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sterish_pipeline.content_hash import content_hash, hash_bytes, read_skill_files
from sterish_pipeline.intake.normalize import NormalizedSkill, SourceKind, normalize

INDEX_FILENAME = "index.json"
CORPUS_SCHEMA = "sterish.corpus/v1"


@dataclass
class Provenance:
    """Where an entry came from, and how to check it did not change."""

    source: str
    source_url: str = ""
    fetched_at: str = ""
    upstream_etag: str = ""
    upstream_last_modified: str = ""
    note: str = ""


@dataclass
class CorpusEntry:
    """One auditable skill in the corpus."""

    skill_id: str
    version: str
    kind: str
    path: str
    content_hash: str
    file_digests: dict[str, str] = field(default_factory=dict)
    expected_verdict: str = ""
    label: str = ""
    provenance: Provenance = field(default_factory=Provenance)

    @property
    def is_poisoned(self) -> bool:
        return self.label == "poisoned"

    def to_json(self) -> dict:
        payload = asdict(self)
        payload["provenance"] = asdict(self.provenance)
        return payload

    @classmethod
    def from_json(cls, payload: dict) -> CorpusEntry:
        data = dict(payload)
        data["provenance"] = Provenance(**data.get("provenance", {}))
        return cls(**data)


class CorpusError(RuntimeError):
    """The corpus on disk does not match its index."""


class Corpus:
    """Read/write access to a corpus directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_FILENAME

    # --- reading -------------------------------------------------------------

    def load(self) -> list[CorpusEntry]:
        if not self.index_path.exists():
            raise CorpusError(f"no corpus index at {self.index_path}")
        document = json.loads(self.index_path.read_text(encoding="utf-8"))
        schema = document.get("schema")
        if schema != CORPUS_SCHEMA:
            raise CorpusError(f"unsupported corpus schema {schema!r}, expected {CORPUS_SCHEMA!r}")
        return [CorpusEntry.from_json(e) for e in document.get("entries", [])]

    def read_files(self, entry: CorpusEntry) -> dict[str, bytes]:
        target = self.root / entry.path
        if not target.exists():
            raise CorpusError(f"{entry.skill_id}: missing snapshot at {target}")
        return read_skill_files(target)

    def normalized(self, entry: CorpusEntry) -> NormalizedSkill:
        return normalize(
            entry.skill_id,
            entry.version,
            self.read_files(entry),
            SourceKind(entry.kind),
        )

    # --- integrity -----------------------------------------------------------

    def verify(self, entry: CorpusEntry) -> list[str]:
        """Recompute hashes from the snapshot bytes. Returns problems found."""
        problems: list[str] = []
        try:
            files = self.read_files(entry)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            return [f"{entry.skill_id}: cannot read snapshot: {exc}"]

        recomputed = content_hash(files)
        if recomputed != entry.content_hash:
            problems.append(
                f"{entry.skill_id}: content_hash mismatch — index says "
                f"{entry.content_hash}, bytes give {recomputed}"
            )

        for path, digest in sorted(entry.file_digests.items()):
            if path not in files:
                problems.append(f"{entry.skill_id}: indexed file missing on disk: {path}")
            elif hash_bytes(files[path]) != digest:
                problems.append(f"{entry.skill_id}: file digest mismatch: {path}")

        for path in sorted(set(files) - set(entry.file_digests)):
            problems.append(f"{entry.skill_id}: file on disk is not in the index: {path}")

        return problems

    def verify_all(self) -> list[str]:
        problems: list[str] = []
        seen_ids: set[str] = set()
        for entry in self.load():
            if entry.skill_id in seen_ids:
                problems.append(f"duplicate skill_id in index: {entry.skill_id}")
            seen_ids.add(entry.skill_id)
            problems.extend(self.verify(entry))
        return problems

    # --- writing -------------------------------------------------------------

    def write_entry(
        self,
        skill_id: str,
        version: str,
        kind: SourceKind,
        files: dict[str, bytes],
        relative_path: str,
        provenance: Provenance,
        label: str = "",
        expected_verdict: str = "",
    ) -> CorpusEntry:
        """Write snapshot bytes to disk and return the index entry for them."""
        target = self.root / relative_path
        target.mkdir(parents=True, exist_ok=True)
        for path, data in files.items():
            destination = target / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Binary write: never let the platform translate line endings, or
            # the recorded content_hash stops matching the bytes on disk.
            destination.write_bytes(data)

        return CorpusEntry(
            skill_id=skill_id,
            version=version,
            kind=kind.value,
            path=relative_path,
            content_hash=content_hash(files),
            file_digests={path: hash_bytes(data) for path, data in sorted(files.items())},
            expected_verdict=expected_verdict,
            label=label,
            provenance=provenance,
        )

    def save_index(self, entries: list[CorpusEntry], generated_at: str) -> None:
        ordered = sorted(entries, key=lambda e: e.skill_id)
        document = {
            "schema": CORPUS_SCHEMA,
            "content_hash_spec": "sterish-content-hash/v1",
            "generated_at": generated_at,
            "count": len(ordered),
            "entries": [e.to_json() for e in ordered],
        }
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
