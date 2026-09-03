#!/usr/bin/env python3
"""Sterish canonical ``content_hash`` v1 — reference implementation (Python).

Normative spec: ``docs/specs/content-hash.md``. If this file and the spec ever
disagree, the spec wins and this file is the bug.

CLI
---
    python3 content_hash.py <dir>              # hash a skill directory, print 64 hex chars
    python3 content_hash.py --vectors [path]   # run the shared test vectors, print report lines
    python3 content_hash.py --regen [path]     # recompute expected_sha256 in the vector file

The ``--vectors`` report is byte-for-byte comparable with the TypeScript and
Rust reference implementations; ``scripts/verify-content-hash.sh`` diffs them.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

#: Domain-separation prefix. 24 bytes, trailing newline included.
MAGIC = b"sterish-content-hash/v1\n"
assert len(MAGIC) == 24, "MAGIC must be exactly 24 bytes"

#: Directories dropped by the packager BEFORE hashing (not part of the hash).
EXCLUDED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "target"})
#: File names dropped by the packager BEFORE hashing.
EXCLUDED_FILES = frozenset({".DS_Store"})
#: File suffixes dropped by the packager BEFORE hashing.
EXCLUDED_SUFFIXES = (".pyc",)


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class ContentHashError(Exception):
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


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------


def u32be(n: int) -> bytes:
    """Unsigned 32-bit big-endian length prefix."""
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
    """Apply the v1 content normalization: CRLF -> LF, CR -> LF, strip trailing LF."""
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NotUtf8(f"content is not valid UTF-8: {exc}") from exc
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return normalized.rstrip(b"\n")


def canonical_bytes(files: Sequence[Tuple[bytes, bytes]]) -> bytes:
    """Build CANON from ``(path_bytes, raw_content)`` pairs. Order of input is irrelevant."""
    if not files:
        raise EmptyFileSet("a skill must contain at least one file")

    seen: set[bytes] = set()
    items: List[Tuple[bytes, bytes]] = []
    for path_bytes, raw in files:
        check_path(path_bytes)
        if path_bytes in seen:
            raise DuplicatePath(f"duplicate path: {path_bytes!r}")
        seen.add(path_bytes)
        items.append((path_bytes, normalize_content(raw)))

    # ASC bytewise on the RAW path bytes. Python's bytes ordering is bytewise.
    items.sort(key=lambda item: item[0])

    buf = bytearray(MAGIC)
    buf += u32be(len(items))
    for path_bytes, content in items:
        buf += u32be(len(path_bytes))
        buf += path_bytes
        buf += u32be(len(content))
        buf += content
    return bytes(buf)


def content_hash(files: Sequence[Tuple[bytes, bytes]]) -> str:
    """64 lowercase hex chars."""
    return hashlib.sha256(canonical_bytes(files)).hexdigest()


# --------------------------------------------------------------------------
# Directory packager
# --------------------------------------------------------------------------


def is_excluded(rel_parts: Sequence[str], name: str) -> bool:
    if any(part in EXCLUDED_DIRS for part in rel_parts):
        return True
    if name in EXCLUDED_FILES:
        return True
    return name.endswith(EXCLUDED_SUFFIXES)


def collect_dir(root: str | os.PathLike[str]) -> List[Tuple[bytes, bytes]]:
    """Walk a skill directory, applying the exclusion list, and return hashable files."""
    root_path = Path(root).resolve()
    out: List[Tuple[bytes, bytes]] = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        rel_dir = Path(dirpath).relative_to(root_path)
        rel_parts = [] if rel_dir == Path(".") else list(rel_dir.parts)
        for name in sorted(filenames):
            if is_excluded(rel_parts, name):
                continue
            rel = "/".join([*rel_parts, name])
            out.append((rel.encode("utf-8"), Path(dirpath, name).read_bytes()))
    return out


def hash_dir(root: str | os.PathLike[str]) -> str:
    return content_hash(collect_dir(root))


# --------------------------------------------------------------------------
# Test-vector runner (shared report format)
# --------------------------------------------------------------------------

DEFAULT_VECTORS = Path(__file__).resolve().parent.parent / "vectors" / "content-hash-vectors.json"


def _files_of(vector: dict) -> List[Tuple[bytes, bytes]]:
    return [
        (f["path"].encode("utf-8"), base64.b64decode(f["content_b64"], validate=True))
        for f in vector["files"]
    ]


def run_vectors(path: Path) -> int:
    doc = json.loads(path.read_text(encoding="utf-8"))
    lines: List[str] = []
    problems: List[str] = []
    hashes: dict[str, str] = {}

    for vector in doc["vectors"]:
        vid = vector["id"]
        got = content_hash(_files_of(vector))
        hashes[vid] = got
        lines.append(f"VECTOR {vid} {got}")
        expected = vector.get("expected_sha256")
        if expected and expected != got:
            problems.append(f"{vid}: expected {expected}, computed {got}")

    for vector in doc["vectors"]:
        vid = vector["id"]
        for other in vector.get("expect_equal_to", []):
            ok = hashes[vid] == hashes[other]
            lines.append(f"RELATION {vid} equals {other} {'OK' if ok else 'FAIL'}")
            if not ok:
                problems.append(f"{vid} must equal {other} but does not")
        for other in vector.get("expect_differs_from", []):
            ok = hashes[vid] != hashes[other]
            lines.append(f"RELATION {vid} differs {other} {'OK' if ok else 'FAIL'}")
            if not ok:
                problems.append(f"{vid} must differ from {other} but does not")

    for case in doc["error_cases"]:
        cid = case["id"]
        want = case["expect_error"]
        try:
            content_hash(_files_of(case))
            got_kind = "NO_ERROR"
        except ContentHashError as exc:
            got_kind = exc.kind
        lines.append(f"ERROR {cid} {got_kind}")
        if got_kind != want:
            problems.append(f"{cid}: expected error {want}, got {got_kind}")

    print("\n".join(lines))
    for problem in problems:
        print(f"python: {problem}", file=sys.stderr)
    return 1 if problems else 0


def regen_vectors(path: Path) -> int:
    doc = json.loads(path.read_text(encoding="utf-8"))
    for vector in doc["vectors"]:
        vector["expected_sha256"] = content_hash(_files_of(vector))
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"regenerated {len(doc['vectors'])} expected_sha256 values in {path}", file=sys.stderr)
    return 0


def main(argv: Sequence[str]) -> int:
    if len(argv) >= 1 and argv[0] == "--vectors":
        return run_vectors(Path(argv[1]) if len(argv) > 1 else DEFAULT_VECTORS)
    if len(argv) >= 1 and argv[0] == "--regen":
        return regen_vectors(Path(argv[1]) if len(argv) > 1 else DEFAULT_VECTORS)
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print(__doc__, file=sys.stderr)
        return 2
    print(hash_dir(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
