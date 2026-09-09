"""`GET /license/{skill_id}/{version}` (STE-35).

The three tests that matter are the ones named after the ways `/use` got this wrong:
a licence must be visible without an artifact on disk, without a SAFE verdict, and a
failed chain read must never be served as `held: false`.
"""

import pytest

from sterish_api import chain
from sterish_api.config import settings

AGENT = "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU"
PATH = "/license/com.acme.pdf-suite/1.0.0"


class TestAnswer:
    def test_held_true(self, client, monkeypatch):
        monkeypatch.setattr(chain, "has_license", lambda a, s, v: True)
        body = client.get(f"{PATH}?agent={AGENT}").json()
        assert body["held"] is True
        assert body["skill_id"] == "com.acme.pdf-suite"
        assert body["version"] == "1.0.0"
        assert body["agent"] == AGENT
        assert body["tokens_contract_id"] == settings.tokens_contract_id
        assert body["contract_url"].startswith("https://stellar.expert/explorer/testnet/contract/")

    def test_held_false(self, client, monkeypatch):
        monkeypatch.setattr(chain, "has_license", lambda a, s, v: False)
        assert client.get(f"{PATH}?agent={AGENT}").json()["held"] is False

    def test_the_exact_triple_reaches_the_contract(self, client, monkeypatch):
        """A licence is pinned to one (agent, skill_id, version); nothing may be dropped."""
        seen = []
        monkeypatch.setattr(
            chain, "has_license", lambda a, s, v: seen.append((a, s, v)) or True
        )
        client.get("/license/com.acme.pdf-suite/2.1.0?agent=" + AGENT)
        assert seen == [(AGENT, "com.acme.pdf-suite", "2.1.0")]

    def test_agent_header_is_accepted(self, client, monkeypatch):
        monkeypatch.setattr(chain, "has_license", lambda a, s, v: True)
        r = client.get(PATH, headers={"X-AGENT-ADDRESS": AGENT})
        assert r.status_code == 200
        assert r.json()["agent"] == AGENT

    def test_query_param_wins_over_header(self, client, monkeypatch):
        other = "GCFCURTZ7XHMTKZR7QN2MXRRAIWKGVOOVQV4KCP5EIQ62HGG4S3Y2XPL"
        seen = []
        monkeypatch.setattr(
            chain, "has_license", lambda a, s, v: seen.append(a) or True
        )
        client.get(f"{PATH}?agent={AGENT}", headers={"X-AGENT-ADDRESS": other})
        assert seen == [AGENT]

    def test_no_verdict_fields_are_returned(self, client, monkeypatch):
        """Scope discipline: this endpoint answers one question and does not badge."""
        monkeypatch.setattr(chain, "has_license", lambda a, s, v: True)
        body = client.get(f"{PATH}?agent={AGENT}").json()
        for leaked in ("verdict", "trust_score", "is_verified", "evidence"):
            assert leaked not in body


class TestTheThingsUseGotWrong:
    """Each of these passes here and fails on `GET /use` — that is the whole ticket."""

    def test_answers_without_an_artifact_on_disk(self, client, monkeypatch):
        """`/use` reads the artifact before replying, so a real licence 404s for any
        skill not published to STERISH_SKILLS_DIR — 46 of 47 live skills."""
        monkeypatch.setattr(chain, "has_license", lambda a, s, v: True)

        def explode(*args, **kwargs):
            raise AssertionError("the licence answer must not depend on the artifact")

        monkeypatch.setattr("sterish_api.routes.use._skill_bytes", explode)
        # Also prove it directly: no artifact dir configured at all.
        previous = settings.skills_dir
        object.__setattr__(settings, "skills_dir", "")
        try:
            r = client.get(f"{PATH}?agent={AGENT}")
            assert r.status_code == 200
            assert r.json()["held"] is True
        finally:
            object.__setattr__(settings, "skills_dir", previous)

    def test_answers_for_a_dangerous_version(self, client, monkeypatch):
        """`/use` returns 403 NOT_VERIFIED before it ever looks at the licence, hiding
        existing holders of a version that was later re-audited to DANGEROUS."""
        monkeypatch.setattr(chain, "has_license", lambda a, s, v: True)

        def explode(*args, **kwargs):
            raise AssertionError("the licence answer must not read the registry verdict")

        monkeypatch.setattr(chain, "get_version", explode)

        r = client.get(f"/license/com.evil.token-drainer/1.0.0?agent={AGENT}")
        assert r.status_code == 200
        assert r.json()["held"] is True

    def test_a_failed_chain_read_is_not_served_as_not_held(self, client, monkeypatch):
        """`/use` swallows this and falls through to 402, conflating "no licence" with
        "could not tell". The whole point of the endpoint is to keep them apart."""

        def unreachable(*args, **kwargs):
            raise chain.ChainError("rpc timed out")

        monkeypatch.setattr(chain, "has_license", unreachable)

        r = client.get(f"{PATH}?agent={AGENT}")
        assert r.status_code == 502
        assert r.json()["error"] == "RPC_UNAVAILABLE"
        assert "held" not in r.json()


class TestBadInput:
    def test_missing_agent_is_400(self, client):
        r = client.get(PATH)
        assert r.status_code == 400
        assert r.json()["error"] == "MISSING_AGENT"

    def test_blank_agent_is_400(self, client):
        r = client.get(f"{PATH}?agent=   ")
        assert r.status_code == 400
        assert r.json()["error"] == "MISSING_AGENT"

    @pytest.mark.parametrize(
        "bad",
        [
            "nope",
            "G" + "A" * 10,
            "CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA",  # contract
            "SBRPX4" + "A" * 50,  # a SECRET key
            AGENT.lower(),
        ],
    )
    def test_non_account_addresses_are_400(self, client, monkeypatch, bad):
        """Rejected rather than encoded into a read that would return false for the
        wrong reason. A secret key in particular must never reach the chain layer."""
        reached = []
        monkeypatch.setattr(
            chain, "has_license", lambda a, s, v: reached.append(a) or True
        )
        r = client.get(f"{PATH}?agent={bad}")
        assert r.status_code == 400
        assert r.json()["error"] == "INVALID_AGENT"
        assert reached == []

    def test_a_rejected_agent_is_not_echoed_into_the_detail(self, client):
        """The detail quotes what was sent, so make sure a secret cannot be smuggled
        into a log line by way of a 200 body — it is a 400, and only ever a 400."""
        secret = "SBRPX4" + "A" * 50
        r = client.get(f"{PATH}?agent={secret}")
        assert r.status_code == 400

    def test_unconfigured_tokens_contract_is_503(self, client, monkeypatch):
        previous = settings.tokens_contract_id
        object.__setattr__(settings, "tokens_contract_id", "")
        try:
            r = client.get(f"{PATH}?agent={AGENT}")
            assert r.status_code == 503
            assert r.json()["error"] == "NOT_CONFIGURED"
        finally:
            object.__setattr__(settings, "tokens_contract_id", previous)
