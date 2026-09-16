"""`GET /licenses?agent=G...` (STE-46), with the tokens contract stubbed.

The tests that matter are the ones about what the list must never do: miss a licence
because its event fell out of the RPC window, shrink because a read failed, or change
because the cache was deleted.
"""

import sqlite3

import pytest

from sterish_api import chain, licenses
from sterish_api.config import settings

AGENT = "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU"
OTHER = "GCFCURTZ7XHMTKZR7QN2MXRRAIWKGVOOVQV4KCP5EIQ62HGG4S3Y2XPL"


def _token(token_id, kind, skill_id, version, owner, minted_at):
    return {
        "token_id": token_id, "kind": kind, "skill_id": skill_id, "version": version,
        "owner": owner, "minted_at": minted_at,
    }


class Tokens:
    """A tokens contract: ids 1..n, never burned, reads counted."""

    def __init__(self, monkeypatch):
        self.records = [
            _token(1, "VERIFIED", "com.acme.pdf-suite", "1.0.0", OTHER, 100),
            _token(2, "LICENSE", "com.acme.pdf-suite", "1.0.0", AGENT, 200),
            _token(3, "LICENSE", "com.acme.pdf-suite", "1.0.0", OTHER, 300),
            _token(4, "LICENSE", "com.acme.weather", "2.0.0", AGENT, 400),
        ]
        self.get_calls: list[int] = []
        self.supply_calls = 0
        self.fail_ids: set[int] = set()
        self.supply_error: Exception | None = None
        monkeypatch.setattr(chain, "total_supply", self.total_supply)
        monkeypatch.setattr(chain, "get_token", self.get_token)

    def total_supply(self):
        self.supply_calls += 1
        if self.supply_error:
            raise self.supply_error
        return len(self.records)

    def get_token(self, token_id):
        self.get_calls.append(token_id)
        if token_id in self.fail_ids:
            raise chain.ChainError(f"rpc timeout on {token_id}")
        return dict(self.records[token_id - 1])

    def mint(self, kind, skill_id, version, owner, minted_at):
        self.records.append(
            _token(len(self.records) + 1, kind, skill_id, version, owner, minted_at)
        )


@pytest.fixture
def tokens(monkeypatch):
    return Tokens(monkeypatch)


def ids(response):
    return [(r["token_id"], r["skill_id"], r["version"]) for r in response.json()["licenses"]]


class TestTheList:
    def test_only_this_agents_licences_newest_first(self, client, tokens):
        r = client.get("/licenses", params={"agent": AGENT})
        assert r.status_code == 200
        assert ids(r) == [(4, "com.acme.weather", "2.0.0"), (2, "com.acme.pdf-suite", "1.0.0")]
        body = r.json()
        assert body["agent"] == AGENT
        assert body["total"] == 2
        assert body["total_supply"] == 4
        assert body["tokens_contract_id"] == settings.tokens_contract_id
        assert body["contract_url"].endswith(settings.tokens_contract_id)

    def test_a_verified_badge_is_not_a_licence(self, client, tokens):
        """Token 1 is OTHER's VERIFIED badge; OTHER holds exactly one licence (3)."""
        assert ids(client.get("/licenses", params={"agent": OTHER})) == [
            (3, "com.acme.pdf-suite", "1.0.0")
        ]

    def test_an_address_with_nothing_gets_an_empty_list_not_an_error(self, client, tokens):
        stranger = "GBFXMHA77OLBYF3JJB43O6CKZ4QR35AAQALJK72MUIHTZNBVAQGTTZWY"
        body = client.get("/licenses", params={"agent": stranger}).json()
        assert body["licenses"] == [] and body["total"] == 0 and body["total_supply"] == 4

    def test_fields_and_iso_time(self, client, tokens):
        row = client.get("/licenses", params={"agent": AGENT}).json()["licenses"][0]
        assert row["minted_at"] == 400
        assert row["minted_at_iso"] == "1970-01-01T00:06:40Z"

    def test_no_verdict_is_joined_in(self, client, tokens):
        """Ownership and verdict are two reads (api-spec §3.8); this is the first only."""
        row = client.get("/licenses", params={"agent": AGENT}).json()["licenses"][0]
        for leaked in ("verdict", "trust_score", "is_verified", "evidence"):
            assert leaked not in row

    def test_the_header_form_works(self, client, tokens):
        r = client.get("/licenses", headers={"X-AGENT-ADDRESS": AGENT})
        assert r.status_code == 200 and r.json()["total"] == 2

    def test_paging(self, client, tokens):
        for n in range(5, 12):
            tokens.mint("LICENSE", f"com.acme.s{n}", "1.0.0", AGENT, 1000 + n)
        first = client.get("/licenses", params={"agent": AGENT, "limit": 3}).json()
        second = client.get("/licenses", params={"agent": AGENT, "start": 3, "limit": 3}).json()
        assert first["total"] == second["total"] == 9
        assert [r["token_id"] for r in first["licenses"]] == [11, 10, 9]
        assert [r["token_id"] for r in second["licenses"]] == [8, 7, 6]


class TestWhereTheListComesFrom:
    def test_a_licence_is_listed_even_when_no_mint_event_was_indexed(self, client, tokens):
        """The reason the list is not built from events: an old licence has none left."""
        row = client.get("/licenses", params={"agent": AGENT}).json()["licenses"][0]
        assert row["token_id"] == 4
        assert row["mint_tx"] is None and row["mint_tx_url"] is None

    def test_an_indexed_mint_event_attaches_its_transaction(self, client, tokens):
        licenses.record_license_event({
            "tokens_contract_id": settings.tokens_contract_id, "agent": AGENT,
            "skill_id": "com.acme.weather", "version": "2.0.0",
            "ledger": 10, "tx_hash": "cd" * 32, "occurred_at": 400,
        })
        rows = client.get("/licenses", params={"agent": AGENT}).json()["licenses"]
        assert rows[0]["mint_tx"] == "cd" * 32
        assert rows[0]["mint_tx_url"].endswith("/tx/" + "cd" * 32)
        assert rows[1]["mint_tx"] is None  # another licence's event is not borrowed

    def test_only_new_ids_are_read_on_the_next_request(self, client, tokens):
        client.get("/licenses", params={"agent": AGENT})
        assert sorted(tokens.get_calls) == [1, 2, 3, 4]
        tokens.get_calls.clear()

        tokens.mint("LICENSE", "com.acme.new", "1.0.0", AGENT, 500)
        r = client.get("/licenses", params={"agent": AGENT})
        assert tokens.get_calls == [5]
        assert ids(r)[0] == (5, "com.acme.new", "1.0.0")

    def test_supply_is_read_live_on_every_request(self, client, tokens):
        client.get("/licenses", params={"agent": AGENT})
        client.get("/licenses", params={"agent": AGENT})
        assert tokens.supply_calls == 2

    def test_deleting_the_cache_does_not_change_the_answer(self, client, tokens, _isolated_db):
        before = client.get("/licenses", params={"agent": AGENT}).json()
        with sqlite3.connect(_isolated_db) as conn:
            conn.execute("DELETE FROM tokens")
            conn.execute("DELETE FROM license_events")
        after = client.get("/licenses", params={"agent": AGENT}).json()
        assert before == after

    def test_records_from_another_tokens_contract_are_not_mixed_in(
        self, client, tokens, monkeypatch
    ):
        client.get("/licenses", params={"agent": AGENT})
        previous = settings.tokens_contract_id
        object.__setattr__(
            settings, "tokens_contract_id",
            "CCHVZRLOAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )
        try:
            tokens.records = [_token(1, "LICENSE", "com.acme.v1-only", "1.0.0", AGENT, 50)]
            assert ids(client.get("/licenses", params={"agent": AGENT})) == [
                (1, "com.acme.v1-only", "1.0.0")
            ]
        finally:
            object.__setattr__(settings, "tokens_contract_id", previous)


class TestAFailedReadIsNeverAShorterList:
    def test_total_supply_failing_is_502(self, client, tokens):
        tokens.supply_error = chain.ChainError("rpc down")
        r = client.get("/licenses", params={"agent": AGENT})
        assert r.status_code == 502
        assert r.json()["error"] == "RPC_UNAVAILABLE"

    def test_one_token_read_failing_is_502_not_the_other_licences(self, client, tokens):
        tokens.fail_ids = {4}
        r = client.get("/licenses", params={"agent": AGENT})
        assert r.status_code == 502
        assert "licenses" not in r.json()

    def test_the_next_request_fills_the_gap(self, client, tokens):
        tokens.fail_ids = {4}
        client.get("/licenses", params={"agent": AGENT})
        tokens.fail_ids = set()
        tokens.get_calls.clear()
        r = client.get("/licenses", params={"agent": AGENT})
        assert r.status_code == 200
        assert 4 in tokens.get_calls
        assert ids(r)[0][0] == 4

    def test_a_contract_refusal_below_supply_is_502_not_skipped(self, client, tokens, monkeypatch):
        """TokenNotFound for an id <= total_supply cannot be "no licence"; ids are dense."""
        real = tokens.get_token

        def refuse(token_id):
            if token_id == 2:
                raise chain.ContractError(2, "TokenNotFound")
            return real(token_id)

        monkeypatch.setattr(chain, "get_token", refuse)
        assert client.get("/licenses", params={"agent": AGENT}).status_code == 502


class TestValidation:
    @pytest.mark.parametrize(
        "params, code",
        [
            ({}, "MISSING_AGENT"),
            ({"agent": "not-an-address"}, "INVALID_AGENT"),
            ({"agent": settings.tokens_contract_id}, "INVALID_AGENT"),
            (
                {"agent": "MA7QYNF7SOWQ3GLR2BGMZEHXAVIRZA4KVWLTJJFC7MGXUA74P7UJUAAAAAAAAAAAAGZFQ"},
                "INVALID_AGENT",
            ),
        ],
    )
    def test_agent_is_required_and_must_be_an_account(self, client, tokens, params, code):
        r = client.get("/licenses", params=params)
        assert r.status_code == 400
        assert r.json()["error"] == code
        assert tokens.supply_calls == 0  # rejected before any chain read

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"start": -1}])
    def test_paging_bounds(self, client, tokens, params):
        assert client.get("/licenses", params={"agent": AGENT, **params}).status_code == 422

    def test_not_configured_is_503(self, client, tokens):
        previous = settings.tokens_contract_id
        object.__setattr__(settings, "tokens_contract_id", "")
        try:
            r = client.get("/licenses", params={"agent": AGENT})
            assert r.status_code == 503
        finally:
            object.__setattr__(settings, "tokens_contract_id", previous)
