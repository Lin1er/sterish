"""The test-namespace rule: which skill_ids are scaffolding, and who agrees.

The registry is append-only and no Sterish contract is upgradeable, so a skill a
test registers on testnet is there for good. 47 such entries had accumulated
against 19 real ones by STE-18. They are filtered rather than deleted, and a
filter only works if the tests register under a prefix it catches — which is what
this file pins.
"""

import pytest

from sterish_pipeline.namespaces import (
    LEGACY_TEST_SKILL_IDS,
    TEST_SKILL_ID_PREFIXES,
    is_test_skill_id,
    new_test_skill_id,
)

#: Every id the 9 Sep 2026 chain read returned, one per shape. The junk column of
#: the audit-evidence table is these plus repetitions of the same three prefixes.
ON_CHAIN_JUNK = [
    "com.sterish.it-safe-skill-1788541727",
    "com.sterish.it-poisoned-pdf-skill-1788541788",
    "com.sterish.e2e-1788541421",
    "com.sterish.canon-safe-1788685783",
    "com.sterish.canon-poisoned-1788685812",
    "com.sterish.weather-lookup",
    "com.evil.token-drainer",
]

#: Entries that must stay visible. The catalog is the product's evidence and the
#: fixtures are what prove the gate works; hiding either empties the dashboard.
ON_CHAIN_REAL = [
    "org.stellar.skills.cross-chain.cctp",
    "org.stellar.skills.smart-contracts.security",
    "com.fixtures.poisoned.token-drainer",
    "com.fixtures.safe.weather-lookup",
    "com.fixtures.demo.release-notes",
    "com.fixtures.demo.changelog-writer",
    "com.fixtures.demo.ledger-inspector",
    "com.fixtures.demo.table-formatter",
]


@pytest.mark.parametrize("skill_id", ON_CHAIN_JUNK)
def test_known_junk_is_caught(skill_id: str) -> None:
    assert is_test_skill_id(skill_id)


@pytest.mark.parametrize("skill_id", ON_CHAIN_REAL)
def test_real_entries_are_not_caught(skill_id: str) -> None:
    assert not is_test_skill_id(skill_id)


def test_the_bare_vendor_namespace_is_not_a_marker() -> None:
    """`com.sterish.` alone must not hide a skill: a real Sterish-published skill
    would live there too. Only the explicit markers count."""
    assert not is_test_skill_id("com.sterish.release-notes")
    assert not is_test_skill_id("com.evil.some-other-skill")


def test_generated_ids_are_caught() -> None:
    for kind in ("it", "e2e", "canon"):
        assert is_test_skill_id(new_test_skill_id(kind, "demo"))


def test_generated_ids_are_unique_per_run() -> None:
    assert new_test_skill_id("it", "demo", 1) != new_test_skill_id("it", "demo", 2)


def test_generated_ids_satisfy_the_frozen_schema_pattern() -> None:
    """verdict.schema.json allows lowercase alphanumerics, hyphens and dots only."""
    import re

    generated = new_test_skill_id("it", "Poisoned_PDF Skill", 1788541788)
    assert re.fullmatch(r"[a-z0-9.-]+", generated), generated


def test_an_unknown_marker_is_refused() -> None:
    with pytest.raises(ValueError, match="not a test-id marker"):
        new_test_skill_id("prod", "demo")


def test_live_orchestration_registers_only_filterable_ids(tmp_path) -> None:
    """The guard that stops the live suite adding to the junk pile.

    It reaches into the live module on purpose: that module is skipped without
    STERISH_LIVE_TESTS=1, so its own id-building would otherwise never be checked
    on a normal run — which is exactly when a drifting prefix would slip through.
    """
    from test_live_orchestration import _fresh_skill

    for fixture in ("safe_skill", "poisoned_pdf_skill"):
        _, skill_id = _fresh_skill(tmp_path / fixture, fixture)
        assert is_test_skill_id(skill_id), skill_id


def test_legacy_ids_are_named_exactly_not_by_prefix() -> None:
    """Widening these into a prefix rule would let the exception grow silently."""
    assert LEGACY_TEST_SKILL_IDS == {
        "com.sterish.weather-lookup",
        "com.evil.token-drainer",
    }
    assert not any(legacy.startswith(TEST_SKILL_ID_PREFIXES) for legacy in LEGACY_TEST_SKILL_IDS)
