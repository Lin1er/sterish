"""Sterish ``content_hash`` v1 — the frozen canonical algorithm.

Normative spec: ``docs/specs/content-hash.md`` (FROZEN, STE-10). Reference
implementation: ``docs/specs/reference/content_hash.py``. If this file and the
spec ever disagree, the spec wins and this file is the bug.

The hash is the byte identity of a skill. It is computed in three places
(pipeline / Rust contract / TypeScript client) and they must agree byte-for-byte,
or ``check(skill)`` lies. This module is the pipeline's implementation; it is
verified against the same shared vectors as the Rust and TypeScript ones.

    CANON = MAGIC
         || u32be(file_count)
         || for each file, sorted ASC bytewise by path_bytes:
                u32be(len(path_bytes))   || path_bytes
                u32be(len(norm_content)) || norm_content

    MAGIC        = b"sterish-content-hash/v1\\n"     (24 bytes, includes the \\n)
    content_hash = sha256(CANON)                    (32 bytes, 64 lowercase hex)

``norm_content`` normalizes line endings (CRLF -> LF, CR -> LF) and strips
trailing newlines; files must be valid UTF-8. skill_id and version are NOT part
of the hash — only the file paths and their normalized bytes are.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path

#: Domain-separation prefix. 24 bytes, trailing newline included.
MAGIC = b"sterish-content-hash/v1\n"
assert len(MAGIC) == 24, "MAGIC must be exactly 24 bytes"

#: Dropped by the packager BEFORE hashing (not part of the algorithm).
EXCLUDED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "target"})
EXCLUDED_FILES = frozenset({".DS_Store"})
EXCLUDED_SUFFIXES = (".pyc",)


class ContentHashError(ValueError):
    """Base class. ``kind`` is the stable, cross-language error name."""

    kind = "ContentHashError"


class EmptyFileSet(ContentHashError):
    kind = "EmptyFileSet"


class DuplicatePath(ContentHashError):
    kind = "DuplicatePath"


class InvalidPath(ContentHashError):
    kind = "InvalidPath"


class NotUtf8(ContentHashError):
    kind = "NotUtf8"


def _u32be(n: int) -> bytes:
    if n < 0 or n > 0xFFFF_FFFF:
        raise ContentHashError(f"value out of u32 range: {n}")
    return struct.pack(">I", n)


def check_path(path_bytes: bytes) -> None:
    """Reject anything that is not a clean, relative, POSIX path."""
    if not path_bytes:
        raise InvalidPath("empty path")
    try:
        text = path_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidPath("path is not valid UTF-8") from exc
    if "\\" in text:
        # A backslash is a legal POSIX filename byte, but rejected on purpose so
        # a Windows-style path never becomes one filename and hashes differently
        # than the same skill packaged on another OS.
        raise InvalidPath(f"backslash is not a path separator: {text!r}")
    if "\x00" in text:
        raise InvalidPath(f"NUL byte in path: {text!r}")
    for part in text.split("/"):
        if part == "":
            raise InvalidPath(f"empty path component (leading/trailing/double slash): {text!r}")
        if part == ".":
            raise InvalidPath(f"'.' component not allowed: {text!r}")
        if part == "..":
            raise InvalidPath(f"'..' component not allowed: {text!r}")


def normalize_content(raw: bytes) -> bytes:
    """v1 content normalization: CRLF -> LF, CR -> LF, strip trailing LF."""
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NotUtf8(f"content is not valid UTF-8: {exc}") from exc
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return normalized.rstrip(b"\n")


def hash_bytes(data: bytes) -> str:
    """SHA-256 of raw bytes as 64 lowercase hex characters (per-file digest)."""
    return hashlib.sha256(data).hexdigest()


def _normalize_files(files: Mapping[str, bytes] | Sequence[tuple[str, bytes]]):
    pairs = files.items() if isinstance(files, Mapping) else files
    seen: set[bytes] = set()
    items: list[tuple[bytes, bytes]] = []
    for path, raw in pairs:
        path_bytes = path.encode("utf-8") if isinstance(path, str) else path
        check_path(path_bytes)
        if path_bytes in seen:
            raise DuplicatePath(f"duplicate path: {path_bytes!r}")
        seen.add(path_bytes)
        items.append((path_bytes, normalize_content(raw)))
    if not items:
        raise EmptyFileSet("a skill must contain at least one file")
    # ASC bytewise on the RAW path bytes (Python bytes ordering is bytewise).
    items.sort(key=lambda item: item[0])
    return items


def canonical_bytes(files: Mapping[str, bytes] | Sequence[tuple[str, bytes]]) -> bytes:
    """Build CANON from ``{path: raw_bytes}``. Input order is irrelevant."""
    items = _normalize_files(files)
    buf = bytearray(MAGIC)
    buf += _u32be(len(items))
    for path_bytes, content in items:
        buf += _u32be(len(path_bytes))
        buf += path_bytes
        buf += _u32be(len(content))
        buf += content
    return bytes(buf)


def content_hash(files: Mapping[str, bytes] | Sequence[tuple[str, bytes]]) -> str:
    """Compute ``content_hash`` for an in-memory skill. 64 lowercase hex chars.

    Args:
        files: ``{relative_path: raw_file_bytes}``, at least one entry. skill_id
            and version are intentionally NOT arguments — they are not part of
            the byte identity of the skill (see the frozen spec).
    """
    return hash_bytes(canonical_bytes(files))


def _is_excluded(rel_parts: Sequence[str], name: str) -> bool:
    if any(part in EXCLUDED_DIRS for part in rel_parts):
        return True
    if name in EXCLUDED_FILES:
        return True
    return name.endswith(EXCLUDED_SUFFIXES)


def read_skill_files(root: Path | str) -> dict[str, bytes]:
    """Read every hashable file under ``root`` into ``{path: raw_bytes}``.

    Applies the packager exclusion list. Symlinks are skipped: they carry no
    content of their own and would let a skill hash bytes outside its root.
    """
    root_path = Path(root)
    if root_path.is_file():
        return {root_path.name: root_path.read_bytes()}
    if not root_path.is_dir():
        raise ContentHashError(f"not a file or directory: {root_path}")

    files: dict[str, bytes] = {}
    for path in sorted(root_path.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(root_path)
        rel_parts = list(rel.parts[:-1])
        if _is_excluded(rel_parts, path.name):
            continue
        files[rel.as_posix()] = path.read_bytes()

    if not files:
        raise EmptyFileSet(f"no hashable files found under {root_path}")
    return files


def content_hash_path(root: Path | str) -> str:
    """Compute ``content_hash`` for a skill on disk."""
    return content_hash(read_skill_files(root))
