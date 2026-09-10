"""The OpenAI-compatible stage-3 backend (STE-38).

Two things are being defended here, and only one of them is "does the call work".

The first is **fail-soft**: every way this client can fail — no key, a network error, a
non-200, a non-JSON body, a missing tool call, truncated arguments — has to surface as
`LLMUnavailable`, which `synthesize_with_llm` turns into a note and a deterministic
baseline. An audit pipeline that stops working when a third-party gateway does is not an
audit pipeline.

The second is that the model stays **advisory**. It may tighten a verdict and may never
loosen one. That property is what lets `docs/audit-evidence.md` claim the poisoned gate is
deterministic even with a model in the loop.
"""

import json

import httpx
import pytest

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.llm import (
    EMIT_VERDICT_TOOL,
    LLMUnavailable,
    OpenAICompatibleClient,
    api_key_present,
    as_openai_tool,
    default_client,
)

KEY_VARS = ("LLM_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture
def key(monkeypatch):
    for name in KEY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-a-real-one")


def _response(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload, request=httpx.Request("POST", "https://x/y"))


def _tool_call(arguments: str, name: str = "emit_verdict") -> dict:
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {"tool_calls": [{"function": {"name": name, "arguments": arguments}}]},
            }
        ]
    }


VALID_ARGS = json.dumps(
    {
        "verdict": "DANGEROUS",
        "risk": "critical",
        "score": 5,
        "recommendation": "BLOCK",
        "rationale": "The description asks the agent to read ~/.ssh/id_rsa and upload it.",
    }
)


class TestToolTranslation:
    """The schemas are authored once in Anthropic's shape and translated, not duplicated."""

    def test_translation_preserves_the_schema_exactly(self):
        translated = as_openai_tool(EMIT_VERDICT_TOOL)
        assert translated["type"] == "function"
        assert translated["function"]["name"] == EMIT_VERDICT_TOOL["name"]
        assert translated["function"]["parameters"] is EMIT_VERDICT_TOOL["input_schema"]
        assert translated["function"]["strict"] is True

    def test_the_schema_stays_closed(self):
        """`strict` is only meaningful with additionalProperties:false and a full required
        list — that combination is what makes the returned JSON trustworthy."""
        schema = as_openai_tool(EMIT_VERDICT_TOOL)["function"]["parameters"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


class TestHappyPath:
    def test_returns_the_parsed_arguments(self, key, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _response(_tool_call(VALID_ARGS)))
        result = OpenAICompatibleClient().call_tool(
            "system", {"p": 1}, EMIT_VERDICT_TOOL, PipelineConfig()
        )
        assert result["verdict"] == "DANGEROUS"
        assert result["score"] == 5

    def test_the_call_forces_the_tool_and_never_leaks_the_key_into_the_body(
        self, key, monkeypatch
    ):
        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["json"] = kwargs["json"]
            captured["headers"] = kwargs["headers"]
            return _response(_tool_call(VALID_ARGS))

        monkeypatch.setattr(httpx, "post", fake_post)
        cfg = PipelineConfig(llm_base_url="https://gateway.example/v1", llm_model="m/x")
        OpenAICompatibleClient().call_tool("sys", {"p": 1}, EMIT_VERDICT_TOOL, cfg)

        assert captured["url"] == "https://gateway.example/v1/chat/completions"
        assert captured["json"]["model"] == "m/x"
        # Forced, not hoped for: an unforced model can answer in prose.
        assert captured["json"]["tool_choice"]["function"]["name"] == "emit_verdict"
        assert captured["headers"]["Authorization"].startswith("Bearer ")
        # The key belongs in the header and nowhere else.
        assert "test-key-not-a-real-one" not in json.dumps(captured["json"])

    def test_trailing_slash_on_the_base_url_does_not_double_up(self, key, monkeypatch):
        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            return _response(_tool_call(VALID_ARGS))

        monkeypatch.setattr(httpx, "post", fake_post)
        cfg = PipelineConfig(llm_base_url="https://gateway.example/v1/")
        OpenAICompatibleClient().call_tool("s", {}, EMIT_VERDICT_TOOL, cfg)
        assert captured["url"] == "https://gateway.example/v1/chat/completions"


class TestFailSoft:
    """Every one of these must raise LLMUnavailable, which the caller turns into a note."""

    def test_no_key(self, monkeypatch):
        for name in KEY_VARS:
            monkeypatch.delenv(name, raising=False)
        with pytest.raises(LLMUnavailable, match="LLM_API_KEY"):
            OpenAICompatibleClient()

    def test_network_error(self, key, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("dns failure")

        monkeypatch.setattr(httpx, "post", boom)
        with pytest.raises(LLMUnavailable):
            OpenAICompatibleClient().call_tool("s", {}, EMIT_VERDICT_TOOL, PipelineConfig())

    @pytest.mark.parametrize("status", [401, 402, 429, 500, 503])
    def test_non_200(self, key, monkeypatch, status):
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _response({"error": "x"}, status))
        with pytest.raises(LLMUnavailable, match=str(status)):
            OpenAICompatibleClient().call_tool("s", {}, EMIT_VERDICT_TOOL, PipelineConfig())

    def test_an_error_body_is_not_echoed(self, key, monkeypatch):
        """A gateway may quote the request back. Only the status may reach a log."""
        leak = {"error": {"message": "bad key test-key-not-a-real-one"}}
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _response(leak, 401))
        with pytest.raises(LLMUnavailable) as excinfo:
            OpenAICompatibleClient().call_tool("s", {}, EMIT_VERDICT_TOOL, PipelineConfig())
        assert "test-key-not-a-real-one" not in str(excinfo.value)

    def test_body_is_not_json(self, key, monkeypatch):
        bad = httpx.Response(200, text="<html>gateway</html>",
                             request=httpx.Request("POST", "https://x/y"))
        monkeypatch.setattr(httpx, "post", lambda *a, **k: bad)
        with pytest.raises(LLMUnavailable, match="not JSON"):
            OpenAICompatibleClient().call_tool("s", {}, EMIT_VERDICT_TOOL, PipelineConfig())

    @pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": [{}]}])
    def test_malformed_envelope(self, key, monkeypatch, payload):
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _response(payload))
        with pytest.raises(LLMUnavailable):
            OpenAICompatibleClient().call_tool("s", {}, EMIT_VERDICT_TOOL, PipelineConfig())

    def test_model_answered_in_prose_instead_of_calling_the_tool(self, key, monkeypatch):
        prose = {
            "choices": [{"finish_reason": "stop", "message": {"content": "I think it is fine"}}]
        }
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _response(prose))
        with pytest.raises(LLMUnavailable, match="no emit_verdict tool call"):
            OpenAICompatibleClient().call_tool("s", {}, EMIT_VERDICT_TOOL, PipelineConfig())

    def test_truncated_arguments(self, key, monkeypatch):
        """OpenAI returns arguments as a JSON *string*, so truncation surfaces here."""
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _response(_tool_call('{"verdict": "SA')))
        with pytest.raises(LLMUnavailable, match="not valid JSON"):
            OpenAICompatibleClient().call_tool("s", {}, EMIT_VERDICT_TOOL, PipelineConfig())

    def test_arguments_that_are_not_an_object(self, key, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _response(_tool_call('["SAFE"]')))
        with pytest.raises(LLMUnavailable, match="not an object"):
            OpenAICompatibleClient().call_tool("s", {}, EMIT_VERDICT_TOOL, PipelineConfig())

    def test_a_different_tool_name_is_not_accepted(self, key, monkeypatch):
        monkeypatch.setattr(
            httpx, "post", lambda *a, **k: _response(_tool_call(VALID_ARGS, name="something_else"))
        )
        with pytest.raises(LLMUnavailable):
            OpenAICompatibleClient().call_tool("s", {}, EMIT_VERDICT_TOOL, PipelineConfig())


class TestBackendSelection:
    def test_llm_key_selects_the_openai_client(self, monkeypatch):
        for name in KEY_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("LLM_API_KEY", "x")
        assert isinstance(default_client(), OpenAICompatibleClient)

    def test_llm_key_wins_when_both_are_set(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "x")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
        assert isinstance(default_client(), OpenAICompatibleClient)

    def test_either_variable_counts_as_configured(self, monkeypatch):
        for name in KEY_VARS:
            monkeypatch.delenv(name, raising=False)
        assert api_key_present() is False
        monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
        assert api_key_present() is True
