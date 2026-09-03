"""Bridge to the FROZEN specs in ``docs/specs/``.

The pipeline must never re-implement anything that ``docs/specs/`` already freezes,
because a second implementation is a second place for the value to drift. Concretely:

* ``content_hash`` is computed by loading ``docs/specs/reference/content_hash.py`` and
  calling its ``hash_dir``. Not by a copy of the algorithm living in this package.
* verdict documents are validated against ``docs/specs/verdict.schema.json`` using the
  validator factory in ``docs/specs/examples/validate_examples.py``, which already carries
  a dependency-free fallback checker for the draft 2020-12 subset the schema uses.

Both files are loaded by path at runtime (they are documentation, not an installed
package), so this module owns the repo-root lookup.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

#: Marker that identifies the repository root when walking up from this file.
_ROOT_MARKER = Path("docs") / "specs" / "verdict.schema.json"


class SpecsNotFound(RuntimeError):
    """Raised when the frozen specs directory cannot be located.

    Deliberately fatal: silently falling back to a private implementation of
    ``content_hash`` is exactly the drift this module exists to prevent.
    """


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Walk up from this file until the frozen spec tree is visible."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / _ROOT_MARKER).is_file():
            return candidate
    raise SpecsNotFound(
        f"could not locate {_ROOT_MARKER} above {here}; "
        "the pipeline must run from inside the sterish repository"
    )


def schema_path() -> Path:
    """Path of the frozen verdict JSON Schema (STE-10)."""
    return repo_root() / "docs" / "specs" / "verdict.schema.json"


def _load_module(path: Path, name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SpecsNotFound(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def content_hash_module() -> ModuleType:
    """The frozen Python reference implementation of ``content_hash`` v1."""
    path = repo_root() / "docs" / "specs" / "reference" / "content_hash.py"
    if not path.is_file():
        raise SpecsNotFound(f"missing frozen reference implementation: {path}")
    return _load_module(path, "_sterish_frozen_content_hash")


def hash_dir(root: Path | str) -> str:
    """``content_hash`` v1 of a skill directory. 64 lowercase hex characters.

    Thin delegation to ``docs/specs/reference/content_hash.py::hash_dir`` so that the
    pipeline, the contract and the dashboard can never disagree about skill identity.
    """
    return content_hash_module().hash_dir(root)


@lru_cache(maxsize=1)
def _validate_examples_module() -> ModuleType:
    path = repo_root() / "docs" / "specs" / "examples" / "validate_examples.py"
    if not path.is_file():
        raise SpecsNotFound(f"missing schema validator helper: {path}")
    return _load_module(path, "_sterish_frozen_validate_examples")


@lru_cache(maxsize=2)
def _validator(pointer: str | None) -> Callable[[Any], str | None]:
    import json

    root = json.loads(schema_path().read_text())
    run, _engine = _validate_examples_module().make_validator(root, pointer)
    return run


def schema_error(document: Any, submittable: bool = False) -> str | None:
    """Validate a verdict document against the frozen schema.

    Returns ``None`` when the document is valid, otherwise a human-readable message.
    ``submittable=True`` additionally applies the ``$defs/SubmittableVerdict`` profile,
    which is what the on-chain submitter validates against (it rejects ``UNAUDITED``).
    """
    base = _validator(None)(document)
    if base is not None:
        return base
    if submittable:
        return _validator("#/$defs/SubmittableVerdict")(document)
    return None


def validate_verdict_document(document: Any, submittable: bool = False) -> None:
    """Raise ``ValueError`` when ``document`` does not satisfy the frozen schema."""
    err = schema_error(document, submittable=submittable)
    if err is not None:
        raise ValueError(f"verdict document rejected by frozen schema: {err}")
