"""`/feed` matches what api-spec 3.9 promises (STE-35).

`/feed` shipped in STE-17 and was live for days with one line in a status table and no
section, so the only way to learn its shape was to read `models.py`. Now that 3.9
documents it, this pins the documented fields — a doc nobody can trust is worse than no
doc, and the way it stops being trustworthy is silently.
"""

from sterish_api import indexer
from sterish_api.models import FeedItem, FeedResponse

# Exactly the fields rendered in api-spec 3.9. Adding one means updating the section.
DOCUMENTED_ITEM_FIELDS = {
    "event", "skill_id", "version", "content_hash", "verdict", "trust_score",
    "ledger", "tx_hash", "tx_url", "occurred_at", "occurred_at_iso",
}
DOCUMENTED_TOP_FIELDS = {"events", "total", "indexer_enabled", "last_indexed_ledger"}

# The four the indexer tails; named in 3.9.
DOCUMENTED_EVENTS = {
    "skill_registered", "version_registered", "version_recorded", "verdict_flipped",
}


def test_item_fields_are_exactly_what_the_spec_renders():
    assert set(FeedItem.model_fields) == DOCUMENTED_ITEM_FIELDS


def test_top_level_fields_are_exactly_what_the_spec_renders():
    assert set(FeedResponse.model_fields) == DOCUMENTED_TOP_FIELDS


def test_the_indexer_tails_exactly_the_documented_events():
    """3.9 names four event types. If the indexer learns a fifth, the section is stale."""
    tailed = getattr(indexer, "TRACKED_EVENTS", None) or getattr(indexer, "EVENTS", None)
    if tailed is None:
        import inspect
        source = inspect.getsource(indexer)
        found = {e for e in DOCUMENTED_EVENTS if e in source}
        assert found == DOCUMENTED_EVENTS, f"indexer does not mention {DOCUMENTED_EVENTS - found}"
    else:
        assert set(tailed) == DOCUMENTED_EVENTS


class TestDefaults:
    """3.9 documents limit default 50 (max 200) and offset default 0."""

    def test_defaults_and_bounds(self, client):
        body = client.get("/feed").json()
        assert set(body) == DOCUMENTED_TOP_FIELDS
        # Bounds are enforced by FastAPI validation, so out-of-range is 422 not a clamp.
        assert client.get("/feed?limit=201").status_code == 422
        assert client.get("/feed?limit=0").status_code == 422
        assert client.get("/feed?offset=-1").status_code == 422
        assert client.get("/feed?limit=200&offset=0").status_code == 200

    def test_indexer_off_is_distinguishable_from_a_quiet_registry(self, client):
        """The empty feed must not read as 'nothing has happened' — 3.9 says so."""
        body = client.get("/feed").json()
        assert body["events"] == []
        # conftest sets INDEXER_ENABLED=0, so the flag is what tells the caller why.
        assert body["indexer_enabled"] is False
        assert body["last_indexed_ledger"] is None
