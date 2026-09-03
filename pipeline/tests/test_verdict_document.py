"""VerdictDocument must mirror docs/specs/verdict.schema.json exactly.

Parity is tested in both directions against the frozen examples: whatever the schema
accepts pydantic must accept, and whatever the schema rejects pydantic must reject. A model
that is merely "close" to the schema is worse than no model, because it moves the failure
from construction time to the boundary — or past it.
"""

import json

import pytest
from pydantic import ValidationError

from sterish_pipeline import specs
from sterish_pipeline.models import (
    Capability,
    Finding,
    Recommendation,
    Risk,
    Severity,
    Verdict,
    VerdictDocument,
    to_verdict_json,
)

EXAMPLES = specs.repo_root() / "docs/specs/examples"


def _doc(**overrides) -> VerdictDocument:
    base = dict(
        skill_id="com.sterish.example",
        version="1.0.0",
        content_hash="a" * 64,
        verdict=Verdict.SAFE,
        risk=Risk.NONE,
        score=100,
        capabilities=[],
        findings=[],
        recommendation=Recommendation.ALLOW,
        evidence_hash="b" * 64,
    )
    base.update(overrides)
    return VerdictDocument(**base)


class TestParityWithFrozenExamples:
    @pytest.mark.parametrize("name", [p.name for p in sorted(EXAMPLES.glob("valid-*.json"))])
    def test_valid_examples_round_trip(self, name: str):
        raw = json.loads((EXAMPLES / name).read_text())
        doc = VerdictDocument.model_validate(raw)
        assert to_verdict_json(doc) == raw
        assert specs.schema_error(to_verdict_json(doc)) is None

    @pytest.mark.parametrize("name", [p.name for p in sorted(EXAMPLES.glob("invalid-*.json"))])
    def test_invalid_examples_are_rejected_by_pydantic_too(self, name: str):
        raw = json.loads((EXAMPLES / name).read_text())
        with pytest.raises(ValidationError):
            VerdictDocument.model_validate(raw)

    def test_unaudited_example_is_a_legal_document(self):
        raw = json.loads((EXAMPLES / "submittable-invalid-unaudited.json").read_text())
        doc = VerdictDocument.model_validate(raw)
        assert doc.verdict is Verdict.UNAUDITED
        assert specs.schema_error(to_verdict_json(doc)) is None
        assert specs.schema_error(to_verdict_json(doc), submittable=True) is not None


class TestFieldConstraints:
    def test_score_above_100_rejected(self):
        with pytest.raises(ValidationError):
            _doc(score=101)

    def test_uppercase_hash_rejected(self):
        with pytest.raises(ValidationError):
            _doc(content_hash="A" * 64)

    def test_short_hash_rejected(self):
        with pytest.raises(ValidationError):
            _doc(evidence_hash="a" * 63)

    def test_non_reverse_domain_skill_id_rejected(self):
        with pytest.raises(ValidationError):
            _doc(skill_id="notadomain")

    def test_non_semver_version_rejected(self):
        with pytest.raises(ValidationError):
            _doc(version="v1")

    def test_extra_property_rejected(self):
        with pytest.raises(ValidationError):
            VerdictDocument.model_validate({**to_verdict_json(_doc()), "report_uri": "x"})

    def test_stage_4_finding_rejected(self):
        with pytest.raises(ValidationError):
            Finding(stage=4, severity=Severity.LOW, description="d", evidence="e")

    def test_empty_evidence_rejected(self):
        with pytest.raises(ValidationError):
            Finding(stage=1, severity=Severity.LOW, description="d", evidence="")


class TestSerialization:
    def test_capability_omitted_when_none(self):
        doc = _doc(
            findings=[Finding(stage=2, severity=Severity.HIGH, description="d", evidence="e")]
        )
        out = to_verdict_json(doc)
        assert "capability" not in out["findings"][0]
        assert specs.schema_error(out) is None

    def test_capability_present_when_set(self):
        doc = _doc(
            findings=[
                Finding(
                    stage=1,
                    capability=Capability.WALLET_ACCESS,
                    severity=Severity.HIGH,
                    description="d",
                    evidence="e",
                )
            ]
        )
        out = to_verdict_json(doc)
        assert out["findings"][0]["capability"] == "WALLET_ACCESS"
        assert specs.schema_error(out) is None

    def test_enums_serialize_as_plain_strings(self):
        out = to_verdict_json(_doc(verdict=Verdict.DANGEROUS, risk=Risk.CRITICAL))
        assert out["verdict"] == "DANGEROUS"
        assert out["risk"] == "critical"
        assert isinstance(out["verdict"], str)

    def test_spec_version_defaults_to_1_0_0(self):
        assert _doc().spec_version == "1.0.0"
