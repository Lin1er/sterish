"""``content_hash`` v1 for the pipeline — a delegation, not an implementation.

STE-10 froze one reference implementation at
``docs/specs/reference/content_hash.py`` precisely so that the pipeline, the
contract and the dashboard can never disagree about skill identity, and
``sterish_pipeline.specs.hash_dir`` already routes through it.

This module originally carried a second, independent implementation. It agreed
with the reference on all eight frozen vectors, which is exactly what makes a
duplicate dangerous: it passes today and is free to drift tomorrow, and a drift
here silently changes what a registered skill *is*. Only the two convenience
helpers that the intake module needs are real code below; everything else is
re-exported from the frozen reference.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path

from sterish_pipeline.specs import content_hash_module

_ref = content_hash_module()

# Re-exported verbatim from the frozen reference.
ContentHashError = _ref.ContentHashError
EmptyFileSet = _ref.EmptyFileSet
DuplicatePath = _ref.DuplicatePath
InvalidPath = _ref.InvalidPath
NotUtf8 = _ref.NotUtf8

MAGIC = _ref.MAGIC
check_path = _ref.check_path
normalize_content = _ref.normalize_content
hash_dir = _ref.hash_dir
collect_dir = _ref.collect_dir

_FilesArg = Mapping[str, bytes] | Sequence[tuple[str, bytes]]


def _pairs(files: _FilesArg) -> list[tuple[bytes, bytes]]:
    """Adapt ``{path: bytes}`` to the reference's ``[(path_bytes, bytes)]``.

    Ordering, normalisation, duplicate and path validation all stay in the
    reference; this only converts the container and the key type.
    """
    items = files.items() if isinstance(files, Mapping) else files
    return [(p.encode("utf-8") if isinstance(p, str) else p, raw) for p, raw in items]


def canonical_bytes(files: _FilesArg) -> bytes:
    """Canonical byte encoding the hash is taken over."""
    return _ref.canonical_bytes(_pairs(files))


def content_hash(files: _FilesArg) -> str:
    """``content_hash`` v1. 64 lowercase hex characters."""
    return _ref.content_hash(_pairs(files))


def hash_bytes(data: bytes) -> str:
    """SHA-256 of raw bytes as 64 lowercase hex characters (per-file digest).

    Not part of content_hash v1 — used for per-file provenance in the corpus index.
    """
    return hashlib.sha256(data).hexdigest()


def content_hash_path(root: Path | str) -> str:
    """``content_hash`` v1 for a skill on disk, accepting a single file too."""
    return content_hash(read_skill_files(root))


def read_skill_files(root: Path | str) -> dict[str, bytes]:
    """Read every hashable file under ``root`` into ``{path: raw_bytes}``.

    The directory walk and the exclusion list come from the frozen reference, so
    they are defined in exactly one place. Two helper conveniences sit on top:
    a single file is accepted as a one-file skill, and an empty result is
    rejected rather than returned, so a caller cannot silently hash nothing.
    """
    root_path = Path(root)
    if root_path.is_file():
        return {root_path.name: root_path.read_bytes()}
    if not root_path.is_dir():
        raise ContentHashError(f"not a file or directory: {root_path}")

    files = {path.decode("utf-8"): raw for path, raw in collect_dir(root_path)}
    if not files:
        raise EmptyFileSet("a skill must contain at least one file")
    return files
