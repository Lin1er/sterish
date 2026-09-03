"""content_hash v1 conformance against the FROZEN shared vectors.

The normative spec is ``docs/specs/content-hash.md`` and the normative vectors
are ``docs/specs/vectors/content-hash-vectors.json`` (STE-10). This test proves
the pipeline's implementation computes byte-identical hashes to the Rust and
TypeScript reference implementations for every shared vector and error case —
if it drifts, ``check(skill)`` would lie.
"""

import base64
import json
from pathlib import Path

import pytest

from sterish_pipeline.content_hash import (
    MAGIC,
    ContentHashError,
    DuplicatePath,
    EmptyFileSet,
    InvalidPath,
    NotUtf8,
    canonical_bytes,
    content_hash,
    content_hash_path,
    normalize_content,
    read_skill_files,
)

# The frozen vectors live in docs/specs; find the repo root from this test file.
_REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS_PATH = _REPO_ROOT / "docs" / "specs" / "vectors" / "content-hash-vectors.json"
_DOC = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
VECTORS = _DOC["vectors"]
ERROR_CASES = _DOC["error_cases"]

_ERROR_KINDS = {
    "EmptyFileSet": EmptyFileSet,
    "DuplicatePath": DuplicatePath,
    "InvalidPath": InvalidPath,
    "NotUtf8": NotUtf8,
}


def _files(case: dict) -> list[tuple[str, bytes]]:
    # A list of (path, raw_bytes) pairs — not a dict, so the duplicate-path
    # error case (two entries with the same path) survives to the algorithm.
    # base64 is of the RAW bytes (before normalization).
    return [(f["path"], base64.b64decode(f["content_b64"], validate=True)) for f in case["files"]]


class TestFrozenVectors:
    def test_spec_id_and_magic_match(self) -> None:
        assert _DOC["spec"] == "sterish-content-hash/v1"
        assert MAGIC == b"sterish-content-hash/v1\n"
        assert MAGIC.hex() == _DOC["magic_hex"]

    @pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["id"])
    def test_hash_matches_expected(self, vector: dict) -> None:
        assert content_hash(_files(vector)) == vector["expected_sha256"]

    def test_every_vector_is_covered(self) -> None:
        # Guards against the vector file being trimmed to the easy cases.
        required = {
            "single-file",
            "poisoned-token-drainer",
            "multi-file-ordering",
            "non-bmp-path-order",
            "crlf-equals-lf",
            "one-byte-flip",
        }
        assert required <= {v["id"] for v in VECTORS}

    def test_crlf_equals_lf_relation(self) -> None:
        # The spec normalizes line endings, so these two must hash identically.
        crlf = next(v for v in VECTORS if v["id"] == "crlf-equals-lf")
        assert content_hash(_files(crlf)) == crlf["expected_sha256"]


class TestFrozenErrorCases:
    @pytest.mark.parametrize("case", ERROR_CASES, ids=lambda c: c["id"])
    def test_error_kind_matches(self, case: dict) -> None:
        expected = _ERROR_KINDS[case["expect_error"]]
        with pytest.raises(expected):
            content_hash(_files(case))


class TestAlgorithm:
    def test_input_order_does_not_change_the_hash(self) -> None:
        forward = content_hash({"a": b"1", "b": b"2", "c": b"3"})
        reverse = content_hash({"c": b"3", "b": b"2", "a": b"1"})
        assert forward == reverse

    def test_canon_starts_with_magic(self) -> None:
        assert canonical_bytes({"f": b"x"}).startswith(MAGIC)

    def test_crlf_and_lf_normalize_equal(self) -> None:
        assert content_hash({"a": b"one\r\ntwo\r\n"}) == content_hash({"a": b"one\ntwo"})

    def test_trailing_newlines_stripped(self) -> None:
        assert content_hash({"a": b"x\n\n\n"}) == content_hash({"a": b"x"})

    def test_content_change_changes_hash(self) -> None:
        assert content_hash({"a": b"x"}) != content_hash({"a": b"y"})

    def test_path_change_changes_hash(self) -> None:
        assert content_hash({"a": b"x"}) != content_hash({"b": b"x"})

    def test_length_prefix_prevents_concat_ambiguity(self) -> None:
        # ("ab","") must not collide with ("a","b") — the length prefixes differ.
        assert content_hash({"f": b"ab", "g": b""}) != content_hash({"f": b"a", "g": b"b"})

    def test_skill_id_and_version_are_not_in_the_hash(self) -> None:
        # content_hash takes only files — proven by the signature, asserted here
        # so a future signature change is a conscious decision.
        import inspect

        params = list(inspect.signature(content_hash).parameters)
        assert params == ["files"]


class TestValidation:
    def test_non_utf8_content_is_rejected(self) -> None:
        with pytest.raises(NotUtf8):
            content_hash({"a": b"\xff\xfe"})

    @pytest.mark.parametrize(
        "path",
        ["/abs", "../esc", "a/../b", "./a", "a/./b", "", "a//b", "a/", "tools\\z.py"],
    )
    def test_unsafe_paths_are_rejected(self, path: str) -> None:
        with pytest.raises(InvalidPath):
            content_hash({path: b"x"})

    def test_empty_set_is_rejected(self) -> None:
        with pytest.raises(EmptyFileSet):
            content_hash({})

    def test_normalize_content_directly(self) -> None:
        assert normalize_content(b"a\r\nb\r\n") == b"a\nb"
        assert normalize_content(b"a\rb\r") == b"a\nb"
        assert normalize_content(b"a\n\n") == b"a"


class TestOnDisk:
    def test_reads_directory_tree(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "SKILL.md").write_bytes(b"# skill\n")
        (tmp_path / "sub" / "extra.md").write_bytes(b"extra")
        files = read_skill_files(tmp_path)
        assert files == {"SKILL.md": b"# skill\n", "sub/extra.md": b"extra"}

    def test_excludes_checkout_noise(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_bytes(b"[core]")
        (tmp_path / "SKILL.md").write_bytes(b"x")
        assert set(read_skill_files(tmp_path)) == {"SKILL.md"}

    def test_single_file(self, tmp_path: Path) -> None:
        target = tmp_path / "SKILL.md"
        target.write_bytes(b"x")
        assert read_skill_files(target) == {"SKILL.md": b"x"}

    def test_disk_hash_matches_in_memory(self, tmp_path: Path) -> None:
        (tmp_path / "SKILL.md").write_bytes(b"# Example Skill\n\nDoes nothing harmful.\nEnd.\n")
        single = next(v for v in VECTORS if v["id"] == "single-file")
        assert content_hash_path(tmp_path) == single["expected_sha256"]

    def test_empty_directory_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ContentHashError):
            read_skill_files(tmp_path)
