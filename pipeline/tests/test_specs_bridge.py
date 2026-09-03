"""The pipeline must use the FROZEN spec implementations, not private copies."""

import json
from pathlib import Path

import pytest

from sterish_pipeline import specs

POISONED_DIR = Path(__file__).parent / "poisoned_skill"
# Pinned in docs/specs/vectors/content-hash-vectors.json (vector `poisoned-token-drainer`)
# and on-chain in docs/deployments.md. Three places, one number.
POISONED_CONTENT_HASH = "c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0"


class TestRepoRoot:
    def test_repo_root_contains_frozen_specs(self):
        assert specs.schema_path().is_file()
        assert (specs.repo_root() / "docs/specs/reference/content_hash.py").is_file()

    def test_content_hash_module_is_the_frozen_reference(self):
        mod = specs.content_hash_module()
        assert mod.__file__ is not None
        assert mod.__file__.endswith("docs/specs/reference/content_hash.py")
        assert mod.MAGIC == b"sterish-content-hash/v1\n"


class TestContentHash:
    def test_hash_dir_matches_frozen_vector(self):
        assert specs.hash_dir(POISONED_DIR) == POISONED_CONTENT_HASH

    def test_hash_dir_matches_reference_called_directly(self):
        direct = specs.content_hash_module().hash_dir(POISONED_DIR)
        assert specs.hash_dir(POISONED_DIR) == direct

    def test_hash_is_64_lowercase_hex(self):
        h = specs.hash_dir(POISONED_DIR)
        assert len(h) == 64
        assert h == h.lower()
        assert all(c in "0123456789abcdef" for c in h)

    def test_one_byte_flip_changes_hash(self, tmp_path: Path):
        a = tmp_path / "a"
        a.mkdir()
        (a / "SKILL.md").write_text("hello")
        b = tmp_path / "b"
        b.mkdir()
        (b / "SKILL.md").write_text("hellp")
        assert specs.hash_dir(a) != specs.hash_dir(b)


class TestSchemaValidator:
    def test_frozen_valid_examples_are_accepted(self):
        examples = specs.repo_root() / "docs/specs/examples"
        for path in sorted(examples.glob("valid-*.json")):
            assert specs.schema_error(json.loads(path.read_text())) is None, path.name

    def test_frozen_invalid_examples_are_rejected(self):
        examples = specs.repo_root() / "docs/specs/examples"
        for path in sorted(examples.glob("invalid-*.json")):
            assert specs.schema_error(json.loads(path.read_text())) is not None, path.name

    def test_unaudited_is_valid_but_not_submittable(self):
        path = specs.repo_root() / "docs/specs/examples/submittable-invalid-unaudited.json"
        doc = json.loads(path.read_text())
        assert specs.schema_error(doc) is None
        assert specs.schema_error(doc, submittable=True) is not None

    def test_validate_raises_on_bad_document(self):
        with pytest.raises(ValueError):
            specs.validate_verdict_document({"spec_version": "1.0.0"})
