"""Claude API integration for the audit pipeline — advisory, structured and fail-soft.

Three properties, in order of importance:

1. **Fail-soft.** No key, no SDK, a timeout, a malformed answer, an answer that fails schema
   validation — every one of these returns ``None`` and is recorded as a note. The audit
   continues on the deterministic baseline. An audit pipeline that cannot run without a
   third-party API is not an audit pipeline.
2. **Structured.** The model answers by calling a tool whose ``input_schema`` is ``strict``,
   so the response is validated JSON before it reaches the pipeline, not prose to be parsed.
3. **Advisory.** Nothing here decides anything. ``policy.tighten`` merges the answer into the
   deterministic decision by taking the stricter half of each field.

The key is read from ``ANTHROPIC_API_KEY`` and from nowhere else. It is never written to a
config file, never logged and never placed in the verdict document.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import (
    FinalVerdict,
    Recommendation,
    Risk,
    SkillManifest,
    Stage1Result,
    Stage2Result,
)

logger = logging.getLogger(__name__)

API_KEY_ENV = "ANTHROPIC_API_KEY"


class LLMUnavailable(RuntimeError):
    """The model could not be reached or could not be understood. Always non-fatal."""


# --------------------------------------------------------------------------------------
# Prompts (read from pipeline/prompts/, never hardcoded)
# --------------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def prompts_dir() -> Path:
    """Locate ``pipeline/prompts/``.

    Normal case: three levels up from this file (``pipeline/src/sterish_pipeline/llm.py``).
    Fallback: relative to the repository root, so the package still finds its prompts when it
    is imported from an installed copy inside the repo tree.
    """
    local = Path(__file__).resolve().parents[2] / "prompts"
    if local.is_dir():
        return local
    from sterish_pipeline import specs

    return specs.repo_root() / "pipeline" / "prompts"


def load_prompt(name: str) -> str:
    """Read a prompt by file stem, e.g. ``load_prompt("stage3_synthesis")``."""
    path = prompts_dir() / f"{name}.md"
    if not path.is_file():
        raise LLMUnavailable(f"prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# Structured output schemas
# --------------------------------------------------------------------------------------

#: Tool the model must call for stage 3. ``strict`` requires additionalProperties:false and a
#: complete ``required`` list, which is what makes the returned JSON trustworthy.
EMIT_VERDICT_TOOL: dict[str, Any] = {
    "name": "emit_verdict",
    "description": (
        "Emit the final audit verdict for the skill under review. Call exactly once."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "risk", "score", "recommendation", "rationale"],
        "properties": {
            "verdict": {"type": "string", "enum": ["SAFE", "WARNING", "DANGEROUS"]},
            "risk": {
                "type": "string",
                "enum": ["none", "low", "medium", "high", "critical"],
            },
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "recommendation": {"type": "string", "enum": ["ALLOW", "REVIEW", "BLOCK"]},
            "rationale": {
                "type": "string",
                "description": "Two or three sentences naming the evidence that decided it.",
            },
        },
    },
}

REPORT_INJECTION_TOOL: dict[str, Any] = {
    "name": "report_injection_findings",
    "description": (
        "Report prompt-injection findings in the skill's text. Call exactly once; return an "
        "empty array when the text is clean."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["findings"],
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "field_path",
                        "pattern_id",
                        "severity",
                        "description",
                        "evidence",
                    ],
                    "properties": {
                        "field_path": {"type": "string"},
                        "pattern_id": {
                            "type": "string",
                            "enum": [
                                "hidden_block",
                                "html_comment_directive",
                                "ignore_instructions",
                                "credential_path",
                                "wallet_op",
                                "exfiltration",
                                "zero_width",
                                "name_behaviour_mismatch",
                                "undeclared_capability",
                                "other",
                            ],
                        },
                        "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                        "description": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                },
            }
        },
    },
}


# --------------------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------------------


class StructuredClient(Protocol):
    """Anything that can answer a structured request.

    Exists so the tests can inject a fake without a key and without the network. The real
    implementation is :class:`AnthropicClient`.
    """

    def call_tool(
        self, system: str, payload: dict, tool: dict, config: PipelineConfig
    ) -> dict: ...


def api_key_present() -> bool:
    """True when ``ANTHROPIC_API_KEY`` is set and non-empty."""
    return bool(os.environ.get(API_KEY_ENV, "").strip())


class AnthropicClient:
    """Thin wrapper over ``anthropic.Anthropic`` using tool use for structured output."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(API_KEY_ENV, "").strip()
        if not self._api_key:
            raise LLMUnavailable(f"{API_KEY_ENV} is not set")

    def call_tool(
        self, system: str, payload: dict, tool: dict, config: PipelineConfig
    ) -> dict:
        try:
            import anthropic  # noqa: PLC0415  -- optional dependency, imported lazily
        except ImportError as exc:  # pragma: no cover - depends on the install extra
            raise LLMUnavailable(
                "the 'anthropic' package is not installed; install the 'llm' extra"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key, timeout=config.llm_timeout_s)
        message = client.messages.create(
            model=config.llm_model,
            max_tokens=config.llm_max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                }
            ],
        )
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                # Tool inputs are already parsed JSON; never string-match on them.
                return dict(block.input)
        raise LLMUnavailable(
            f"model returned no {tool['name']} tool call (stop_reason="
            f"{getattr(message, 'stop_reason', 'unknown')})"
        )


# --------------------------------------------------------------------------------------
# Stage 3 synthesis
# --------------------------------------------------------------------------------------


@dataclass
class LLMOpinion:
    """A parsed, validated model answer. Advisory only."""

    verdict: FinalVerdict
    risk: Risk
    recommendation: Recommendation
    score: int
    rationale: str
    model: str
    raw: dict = field(default_factory=dict)


def build_synthesis_payload(
    manifest: SkillManifest,
    stage1: Stage1Result,
    stage2: Stage2Result,
    baseline_verdict: str,
    baseline_risk: str,
    baseline_score: int,
    baseline_recommendation: str,
) -> dict:
    """The JSON handed to the stage-3 prompt. Deterministic, so it caches cleanly."""
    return {
        "skill_id": manifest.skill_id,
        "version": manifest.version,
        "manifest": {
            "name": manifest.name,
            "description": manifest.description,
            "permissions": list(manifest.permissions),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "capabilities": [c.value for c in t.capabilities],
                }
                for t in manifest.tools
            ],
        },
        "stage1": {
            "score": stage1.initial_score,
            "text_scanned": stage1.text_scanned,
            "declared_findings": [
                {
                    "capability": f.capability.value,
                    "severity": f.severity.value,
                    "description": f.description,
                }
                for f in stage1.risk_flags
            ],
            "injection_findings": [
                {
                    "pattern_id": f.pattern_id,
                    "severity": f.severity.value,
                    "field_path": f.field_path,
                    "description": f.description,
                    "evidence": f.evidence,
                }
                for f in stage1.injection_findings
            ],
        },
        "stage2": {
            "escaped_sandbox": stage2.escaped_sandbox,
            "behavioral_flags": [
                {
                    "syscall": f.syscall,
                    "severity": f.severity.value,
                    "description": f.description,
                }
                for f in stage2.behavioral_flags
            ],
        },
        "baseline": {
            "verdict": baseline_verdict,
            "risk": baseline_risk,
            "score": baseline_score,
            "recommendation": baseline_recommendation,
        },
    }


def parse_opinion(raw: dict, model: str) -> LLMOpinion:
    """Validate a raw tool input into an :class:`LLMOpinion`.

    Raises :class:`LLMUnavailable` on anything unexpected. Every enum is checked against the
    frozen vocabulary — a model that answers ``"MALICIOUS"`` produces no opinion at all rather
    than a value the schema would later reject at the boundary.
    """
    try:
        verdict = FinalVerdict(str(raw["verdict"]))
        risk = Risk(str(raw["risk"]))
        recommendation = Recommendation(str(raw["recommendation"]))
        score = int(raw["score"])
        rationale = str(raw.get("rationale", "")).strip()
    except (KeyError, ValueError, TypeError) as exc:
        raise LLMUnavailable(f"model answer failed validation: {exc}") from exc
    if not 0 <= score <= 100:
        raise LLMUnavailable(f"model returned score {score}, outside 0..100")
    if not rationale:
        raise LLMUnavailable("model returned an empty rationale")
    return LLMOpinion(
        verdict=verdict,
        risk=risk,
        recommendation=recommendation,
        score=score,
        rationale=rationale,
        model=model,
        raw=dict(raw),
    )


def synthesize_with_llm(
    manifest: SkillManifest,
    stage1: Stage1Result,
    stage2: Stage2Result,
    baseline_verdict: str,
    baseline_risk: str,
    baseline_score: int,
    baseline_recommendation: str,
    config: PipelineConfig | None = None,
    client: StructuredClient | None = None,
) -> tuple[LLMOpinion | None, list[str]]:
    """Ask the model for a second opinion on the verdict.

    Returns ``(opinion, notes)``. ``opinion`` is ``None`` on every failure path; ``notes``
    always explains what happened and belongs in the internal report only — the verdict
    document's schema forbids extra properties, so no LLM metadata may appear in it.
    """
    cfg = config or PipelineConfig()
    notes: list[str] = []

    if not cfg.use_llm:
        notes.append("LLM synthesis disabled by config (use_llm=False)")
        return None, notes

    if client is None:
        if not api_key_present():
            notes.append(
                f"{API_KEY_ENV} not set; running deterministic-only. This is a configured "
                "mode, not an inconclusive attempt, so it does not bias the verdict."
            )
            return None, notes
        try:
            client = AnthropicClient()
        except LLMUnavailable as exc:
            notes.append(f"LLM client unavailable: {exc}")
            return None, notes

    payload = build_synthesis_payload(
        manifest, stage1, stage2, baseline_verdict, baseline_risk,
        baseline_score, baseline_recommendation,
    )
    try:
        system = load_prompt("stage3_synthesis")
        raw = client.call_tool(system, payload, EMIT_VERDICT_TOOL, cfg)
        opinion = parse_opinion(raw, cfg.llm_model)
    except LLMUnavailable as exc:
        notes.append(f"LLM synthesis failed ({exc}); deterministic baseline stands")
        return None, notes
    except Exception as exc:  # fail-soft by design: an audit never dies on a model call
        logger.warning("LLM synthesis raised %s: %s", type(exc).__name__, exc)
        notes.append(
            f"LLM synthesis raised {type(exc).__name__}: {exc}; deterministic baseline stands"
        )
        return None, notes

    notes.append(f"LLM synthesis succeeded with model {cfg.llm_model}")
    return opinion, notes
