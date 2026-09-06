"""The paid path, with the chain and the facilitator stubbed. No network."""

import base64
import json

import pytest

from sterish_api import chain, x402
from sterish_api.config import settings

SAFE = {
    "skill_id": "com.acme.pdf-suite", "version": "1.0.0",
    "content_hash": "a" * 64, "verdict": "SAFE", "trust_score": 88,
    "is_verified": True, "owner": "G" + "A" * 55, "auditor": "G" + "B" * 55,
    "registered_at": 1, "audited_at": 2, "evidence_hash": "b" * 64,
}
DANGEROUS = dict(SAFE, verdict="DANGEROUS", is_verified=False)
AGENT = "GBFXMHA77OLBYF3JJB43O6CKZ4QR35AAQALJK72MUIHTZNBVAQGTTZWY"


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    """A skill on disk whose bytes hash to what the chain says."""
    from sterish_pipeline.content_hash import content_hash

    root = tmp_path / SAFE["skill_id"] / SAFE["version"]
    root.mkdir(parents=True)
    (root / "manifest.json").write_bytes(b'{"skill_id":"com.acme.pdf-suite"}\n')
    digest = content_hash({"manifest.json": (root / "manifest.json").read_bytes()})
    object.__setattr__(settings, "skills_dir", str(tmp_path))
    monkeypatch.setattr(chain, "get_version", lambda s, v: dict(SAFE, content_hash=digest))
    return digest


def _payment_header(payload: dict) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_unpaid_request_gets_a_402_challenge(client, monkeypatch):
    monkeypatch.setattr(chain, "get_version", lambda s, v: SAFE)
    r = client.get(f"/use/{SAFE['skill_id']}/1.0.0")
    assert r.status_code == 402

    required = json.loads(base64.b64decode(r.headers["PAYMENT-REQUIRED"]))
    assert required["x402Version"] == 2
    accepts = required["accepts"][0]
    assert accepts["scheme"] == "exact"
    assert accepts["network"] == "stellar:testnet"
    assert accepts["amount"] == str(settings.price_base_units)


def test_payto_is_a_classic_account_and_asset_is_the_sac(client, monkeypatch):
    """Swapping these two is the documented common stumble, so it is pinned."""
    monkeypatch.setattr(chain, "get_version", lambda s, v: SAFE)
    r = client.get(f"/use/{SAFE['skill_id']}/1.0.0")
    accepts = json.loads(base64.b64decode(r.headers["PAYMENT-REQUIRED"]))["accepts"][0]
    assert accepts["payTo"].startswith("G")
    assert accepts["asset"].startswith("C")


def test_a_dangerous_version_can_never_be_sold(client, monkeypatch):
    """The claim the whole product rests on, at the point money changes hands."""
    monkeypatch.setattr(chain, "get_version", lambda s, v: DANGEROUS)
    r = client.get(f"/use/{SAFE['skill_id']}/1.0.0")
    assert r.status_code == 403
    assert r.json()["error"] == "NOT_VERIFIED"
    assert "PAYMENT-REQUIRED" not in r.headers


def test_an_existing_licence_is_served_without_payment(client, monkeypatch, artifact):
    monkeypatch.setattr(chain, "has_license", lambda a, s, v: True)
    r = client.get(f"/use/{SAFE['skill_id']}/1.0.0", headers={"X-AGENT-ADDRESS": AGENT})
    assert r.status_code == 200
    assert r.headers["X-STERISH-LICENSE"] == "held"


def test_a_facilitator_outage_is_not_reported_as_non_payment(client, monkeypatch, artifact):
    """503, not 402. Telling a buyer who just paid that they did not would invite
    them to pay twice."""
    monkeypatch.setattr(chain, "has_license", lambda a, s, v: False)

    def down(*a, **k):
        raise x402.FacilitatorError("connection refused")

    monkeypatch.setattr(x402, "verify", down)
    r = client.get(
        f"/use/{SAFE['skill_id']}/1.0.0",
        headers={"X-AGENT-ADDRESS": AGENT, "X-PAYMENT": _payment_header({"payload": {}})},
    )
    assert r.status_code == 503
    assert r.json()["error"] == "FACILITATOR_UNAVAILABLE"


def test_a_rejected_payment_is_402_with_the_facilitator_reason(client, monkeypatch, artifact):
    monkeypatch.setattr(chain, "has_license", lambda a, s, v: False)

    def reject(*a, **k):
        raise x402.PaymentInvalid("insufficient_funds")

    monkeypatch.setattr(x402, "verify", reject)
    r = client.get(
        f"/use/{SAFE['skill_id']}/1.0.0",
        headers={"X-AGENT-ADDRESS": AGENT, "X-PAYMENT": _payment_header({"payload": {}})},
    )
    assert r.status_code == 402
    assert r.json()["detail"] == "insufficient_funds"


def test_settlement_is_never_attempted_on_an_invalid_payment(client, monkeypatch, artifact):
    """Settling first would move money for a request about to be refused."""
    monkeypatch.setattr(chain, "has_license", lambda a, s, v: False)
    settled = []

    def reject(*a, **k):
        raise x402.PaymentInvalid("bad")

    monkeypatch.setattr(x402, "verify", reject)
    monkeypatch.setattr(x402, "settle", lambda *a, **k: settled.append(1))
    client.get(
        f"/use/{SAFE['skill_id']}/1.0.0",
        headers={"X-AGENT-ADDRESS": AGENT, "X-PAYMENT": _payment_header({"payload": {}})},
    )
    assert settled == []


def test_a_malformed_payment_header_is_400(client, monkeypatch, artifact):
    monkeypatch.setattr(chain, "has_license", lambda a, s, v: False)
    r = client.get(
        f"/use/{SAFE['skill_id']}/1.0.0",
        headers={"X-AGENT-ADDRESS": AGENT, "X-PAYMENT": "not-base64-json"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "INVALID_PAYMENT"


def test_artifact_that_does_not_match_the_chain_is_never_served(client, monkeypatch, artifact):
    """A buyer must not pay for one artifact and receive another."""
    monkeypatch.setattr(chain, "has_license", lambda a, s, v: True)
    monkeypatch.setattr(chain, "get_version", lambda s, v: dict(SAFE, content_hash="f" * 64))
    r = client.get(f"/use/{SAFE['skill_id']}/1.0.0", headers={"X-AGENT-ADDRESS": AGENT})
    assert r.status_code == 500
    assert r.json()["error"] == "ARTIFACT_HASH_MISMATCH"


class TestHeaderCodec:
    def test_round_trip(self):
        payload = {"x402Version": 2, "accepts": [{"scheme": "exact"}]}
        assert x402.decode_header(x402.encode_header(payload)) == payload

    def test_garbage_raises_rather_than_returning_empty(self):
        with pytest.raises(ValueError):
            x402.decode_header("!!!not base64!!!")
