"""STE-27 — what the rehearsal is allowed to conclude from a `/use` status code.

Steps 4 and 5 buy something. For three runs they tried to buy the brand-new skill the
run had just registered, got a 404, and were recorded RED — which read as "the paid path
is broken" when the paid path was fine. Artifacts reach the API host only through
`intake publish-artifacts`, run there and fed from the corpus committed in this repo, and
every API route is a GET, so nothing the runner does can publish them.

Since STE-42 the API refuses to price what it cannot deliver. That makes a 402 with a
price positive proof the bytes are on the server, and a 404 a statement about publishing
rather than about the verdict. These tests pin that reading, in both directions.
"""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[2] / "docs" / "rehearsal" / "run_rehearsal.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_rehearsal", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


runner = pytest.importorskip("stellar_sdk") and _load()


class FakeResponse:
    def __init__(self, status_code: int, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}


def _payment_required(amount: str) -> dict:
    payload = {"accepts": [{"maxAmountRequired": amount, "asset": "USDC"}]}
    return {"x-payment-required": base64.b64encode(json.dumps(payload).encode()).decode()}


def test_402_with_a_price_means_the_artifact_is_deliverable(monkeypatch):
    monkeypatch.setattr(
        runner, "api_get", lambda *a, **k: FakeResponse(402, _payment_required("1000000"))
    )
    ok, price, why = runner.is_for_sale("com.example.skill", "1.0.0")
    assert ok is True
    assert price == 1_000_000
    assert "deliverable" in why


def test_404_is_about_publishing_not_about_the_verdict(monkeypatch):
    monkeypatch.setattr(runner, "api_get", lambda *a, **k: FakeResponse(404))
    ok, price, why = runner.is_for_sale("com.example.brand-new", "1.0.0")
    assert ok is False
    assert price == 0
    # The message must not claim anything about SAFEness.
    assert "404" in why
    assert "DANGEROUS" not in why.upper()


def test_a_200_is_not_treated_as_for_sale(monkeypatch):
    """A 200 here would mean it was served without payment — not something to buy."""
    monkeypatch.setattr(runner, "api_get", lambda *a, **k: FakeResponse(200))
    ok, _, _ = runner.is_for_sale("com.example.skill", "1.0.0")
    assert ok is False


def test_402_without_a_parseable_price_still_counts_as_for_sale(monkeypatch):
    """The 402 is the signal; a header we cannot decode must not flip the verdict."""
    monkeypatch.setattr(
        runner, "api_get", lambda *a, **k: FakeResponse(402, {"x-payment-required": "not-base64"})
    )
    ok, price, _ = runner.is_for_sale("com.example.skill", "1.0.0")
    assert ok is True
    assert price == 0


def test_a_network_failure_is_not_read_as_not_for_sale_silently(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.RequestException("connection reset")

    monkeypatch.setattr(runner, "api_get", boom)
    ok, _, why = runner.is_for_sale("com.example.skill", "1.0.0")
    assert ok is False
    assert "request failed" in why  # says it could not tell, rather than implying an answer


def test_pick_buyable_prefers_the_first_that_sells_and_records_the_trail(monkeypatch):
    answers = {
        ("com.new", "1.0.0"): FakeResponse(404),
        ("com.catalog.a", "2.0.0"): FakeResponse(404),
        ("com.catalog.b", "3.0.0"): FakeResponse(402, _payment_required("500000")),
    }

    def fake_get(path, **kwargs):
        _, _, rest = path.partition("/use/")
        skill_id, _, version = rest.rpartition("/")
        return answers[(skill_id, version)]

    monkeypatch.setattr(runner, "api_get", fake_get)
    skill_id, version, price, trail = runner.pick_buyable(
        [("com.new", "1.0.0"), ("com.catalog.a", "2.0.0"), ("com.catalog.b", "3.0.0")]
    )
    assert (skill_id, version, price) == ("com.catalog.b", "3.0.0", 500_000)
    # Every attempt is on the record, so the evidence shows what was rejected and why.
    assert len(trail) == 3
    assert "com.new@1.0.0" in trail[0]


def test_pick_buyable_returns_nothing_rather_than_guessing(monkeypatch):
    monkeypatch.setattr(runner, "api_get", lambda *a, **k: FakeResponse(404))
    skill_id, version, price, trail = runner.pick_buyable([("com.a", "1.0.0"), ("com.b", "1.0.0")])
    assert skill_id == ""
    assert version == ""
    assert price == 0
    assert len(trail) == 2
