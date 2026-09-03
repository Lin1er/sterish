#!/usr/bin/env python3
"""Prove that docs/specs/verdict.schema.json actually accepts and rejects what it claims.

    python3 docs/specs/examples/validate_examples.py

Exit code 0 only when EVERY expectation below holds:

  * valid-*.json      -> MUST validate against the base schema
  * invalid-*.json    -> MUST be rejected by the base schema
  * submittable-invalid-*.json
                      -> MUST validate against the base schema (an UNAUDITED document is a
                         legal artifact) but MUST be rejected by the `SubmittableVerdict`
                         profile, which is what the on-chain submitter validates against.
                         The contract enforces the same rule with InvalidVerdict (error 9).

Uses `jsonschema` when it is installed. When it is not, it falls back to a small built-in
checker covering exactly the draft 2020-12 keywords this schema uses, so the proof runs with
a bare python3 and no network.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE.parent / "verdict.schema.json"

# Why each invalid example must be rejected. Keeping the reason next to the filename means a
# example that starts passing for the WRONG reason still shows up as a surprise in review.
REJECTION_REASON = {
    "invalid-verdict-enum.json": "verdict 'MALICIOUS' is not in the AuditVerdict enum",
    "invalid-score-101.json": "score 101 exceeds maximum 100 (contract: InvalidTrustScore)",
    "invalid-content-hash-not-64-hex.json": "content_hash is 63 chars and uppercase, not 64 lowercase hex",
    "invalid-missing-content-hash.json": "required identity field content_hash is absent",
    "invalid-unknown-capability.json": "'GPU_ACCESS' is not in pipeline models.Capability",
    "invalid-finding-missing-evidence.json": "finding has no evidence pointer, so it is untraceable",
    "invalid-extra-property.json": "report_uri is not part of the frozen shape (additionalProperties: false)",
    "invalid-stage-4.json": "stage 4 does not exist; the pipeline has stages 1-3",
    "submittable-invalid-unaudited.json": "UNAUDITED must never reach submit_verdict",
}


# --------------------------------------------------------------------------------------
# Fallback validator: only the keywords verdict.schema.json actually uses.
# --------------------------------------------------------------------------------------
class Err(Exception):
    pass


def _resolve(root: dict, node: dict) -> dict:
    seen = 0
    while "$ref" in node:
        seen += 1
        if seen > 16:
            raise Err("$ref loop")
        ref = node["$ref"]
        merged = {k: v for k, v in node.items() if k != "$ref"}
        if ref == "#":
            target = root
        elif ref.startswith("#/"):
            target = root
            for part in ref[2:].split("/"):
                target = target[part]
        else:
            raise Err(f"unsupported $ref {ref}")
        node = {**target, **merged}
    return node


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


def _check(root: dict, schema: dict, value, path: str) -> None:
    schema = _resolve(root, schema)

    for sub in schema.get("allOf", []):
        _check(root, sub, value, path)

    if "type" in schema:
        expected = schema["type"]
        py = _TYPES[expected]
        if expected == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise Err(f"{path}: expected integer, got {type(value).__name__}")
        elif expected == "boolean":
            if not isinstance(value, bool):
                raise Err(f"{path}: expected boolean")
        elif not isinstance(value, py) or (expected != "boolean" and isinstance(value, bool)):
            raise Err(f"{path}: expected {expected}, got {type(value).__name__}")

    if "enum" in schema and value not in schema["enum"]:
        raise Err(f"{path}: {value!r} not in enum {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        raise Err(f"{path}: {value!r} != const {schema['const']!r}")

    if isinstance(value, str):
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise Err(f"{path}: {value!r} does not match {schema['pattern']}")
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise Err(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise Err(f"{path}: longer than maxLength {schema['maxLength']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise Err(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise Err(f"{path}: {value} > maximum {schema['maximum']}")

    if isinstance(value, list):
        if schema.get("uniqueItems") and len(
            {json.dumps(v, sort_keys=True) for v in value}
        ) != len(value):
            raise Err(f"{path}: items are not unique")
        if "items" in schema:
            for i, item in enumerate(value):
                _check(root, schema["items"], item, f"{path}[{i}]")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise Err(f"{path}: missing required property {key!r}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(props))
            if extra:
                raise Err(f"{path}: unexpected properties {extra}")
        for key, sub in props.items():
            if key in value:
                _check(root, sub, value[key], f"{path}.{key}" if path else key)


def make_validator(root: dict, pointer: str | None = None):
    """Return (fn(doc) -> None | error string, engine name).

    `pointer` selects a subschema, e.g. "#/$defs/SubmittableVerdict"; None means the whole
    schema. Both engines resolve the internal `{"$ref": "#"}` inside SubmittableVerdict back
    to the root document.
    """
    local_ref = {"$ref": pointer} if pointer else root

    try:
        import jsonschema  # noqa: PLC0415
        from referencing import Registry, Resource  # noqa: PLC0415

        cls = jsonschema.validators.validator_for(root)
        cls.check_schema(root)
        base_uri = root.get("$id", "")
        registry = Registry().with_resource(
            uri=base_uri, resource=Resource.from_contents(root)
        )
        schema = {"$ref": base_uri + pointer} if pointer else root
        validator = cls(schema, registry=registry)

        def run(doc):
            errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
            if not errors:
                return None
            e = errors[0]
            loc = "/".join(str(p) for p in e.path) or "<root>"
            return f"{loc}: {e.message}"

        return run, "jsonschema"
    except ImportError:
        def run(doc):
            try:
                _check(root, local_ref, doc, "")
            except Err as exc:
                return str(exc)
            return None

        return run, "builtin-fallback"


def main() -> int:
    root = json.loads(SCHEMA_PATH.read_text())

    base_run, engine = make_validator(root)
    sub_run, _ = make_validator(root, "#/$defs/SubmittableVerdict")

    print(f"schema : {SCHEMA_PATH}")
    print(f"engine : {engine}\n")

    files = sorted(p for p in HERE.glob("*.json"))
    ok = 0
    failed: list[str] = []

    for path in files:
        doc = json.loads(path.read_text())
        name = path.name

        if name.startswith("valid-"):
            err = base_run(doc)
            if err is None:
                print(f"PASS  accepted  {name}")
                ok += 1
            else:
                print(f"FAIL  accepted? {name} -> unexpectedly rejected: {err}")
                failed.append(name)

        elif name.startswith("submittable-invalid-"):
            base_err = base_run(doc)
            sub_err = sub_run(doc)
            if base_err is None and sub_err is not None:
                print(f"PASS  base-ok/submit-rejected  {name} -> {sub_err}")
                ok += 1
            else:
                print(
                    f"FAIL  {name} -> base={base_err or 'accepted'} "
                    f"submittable={sub_err or 'accepted'}"
                )
                failed.append(name)

        elif name.startswith("invalid-"):
            err = base_run(doc)
            if err is not None:
                print(f"PASS  rejected  {name} -> {err}")
                ok += 1
            else:
                print(f"FAIL  rejected? {name} -> unexpectedly ACCEPTED")
                failed.append(name)
        else:
            print(f"SKIP  {name} (no valid-/invalid- prefix)")
            continue

        reason = REJECTION_REASON.get(name)
        if reason:
            print(f"        expected because: {reason}")

    print(f"\n{ok}/{len(files)} example expectations held")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
