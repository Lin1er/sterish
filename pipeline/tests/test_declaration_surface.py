"""Declaration-consistency detectors need a declaration to be inconsistent with (STE-36).

`exfiltration` and `undeclared_capability` work by comparing prose against
`manifest.permissions` / `manifest.tools`. Run against an Agent Skill published as plain
markdown they compare against an empty set and fire on every URL and every descriptive
sentence — which is how `org.stellar.skills.cross-chain.axelar` came to be graded
DANGEROUS for citing `docs.axelar.dev` in a markdown link.

Two things have to hold at once, and they pull in opposite directions:

* the category error stops (this file's `TestNoSurface`), and
* nothing that actually detects poisoning gets weaker (`TestPoisonedStillCaught`,
  `TestSurfaceStillJudged`).

The second is the one worth guarding, because two poisoned fixtures are structurally
identical to the catalog entries: `agent-skill`, `tools=0`, `permissions=0`.
"""

from pathlib import Path

import pytest

from sterish_pipeline.audit import audit_normalized
from sterish_pipeline.intake.corpus import Corpus
from sterish_pipeline.models import (
    FinalVerdict,
    SkillManifest,
    ToolDef,
)
from sterish_pipeline.stages.injection_rules import (
    TextSource,
    has_declaration_surface,
    scan_injection,
    scan_text,
)

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"

GATED = {"exfiltration", "undeclared_capability"}

# Prose that trips both gated detectors when there is a manifest to contradict.
PROSE = (
    "This skill reads your invoices from https://api.vendor.example/v1/invoices "
    "and makes outbound network requests to fetch them."
)


def _markdown_skill() -> SkillManifest:
    """An Agent Skill with no declaration surface — what skills.stellar.org publishes."""
    return SkillManifest(
        skill_id="com.test.markdown-only",
        version="1.0.0",
        name="Markdown only",
        description=PROSE,
        tools=[],
        permissions=[],
    )


def _declaring_skill() -> SkillManifest:
    """The same prose, from a manifest that does have somewhere to declare things."""
    return SkillManifest(
        skill_id="com.test.declares",
        version="1.0.0",
        name="Declares",
        description=PROSE,
        tools=[ToolDef(name="fetch_invoices", description="Fetch invoices.", capabilities=[])],
        permissions=["file:read"],
    )


class TestSurfaceDetection:
    def test_bare_markdown_has_no_surface(self):
        assert has_declaration_surface(_markdown_skill()) is False

    def test_permissions_are_a_surface(self):
        assert has_declaration_surface(_declaring_skill()) is True

    def test_tools_alone_are_a_surface(self):
        """Shipping tools while declaring no permissions is an omission, not an absence."""
        manifest = _markdown_skill()
        manifest.tools = [ToolDef(name="t", description="d", capabilities=[])]
        assert has_declaration_surface(manifest) is True


class TestNoSurface:
    """The category error stops."""

    def test_gated_detectors_do_not_fire_without_a_surface(self):
        result = scan_injection(_markdown_skill())
        assert not (result.pattern_ids & GATED), result.pattern_ids

    def test_a_cited_url_is_not_an_exfiltration_channel(self):
        """The axelar case, reduced: a markdown link to docs is a citation."""
        manifest = _markdown_skill()
        manifest.description = "[Axelar](https://docs.axelar.dev/) connects Stellar to EVM chains."
        assert "exfiltration" not in scan_injection(manifest).pattern_ids

    def test_scan_text_still_gates_when_asked_directly(self):
        source = TextSource(field_path="manifest.description", text=PROSE)
        with_surface = {f.pattern_id for f in scan_text(source, set())}
        without = {f.pattern_id for f in scan_text(source, set(), declaration_surface=False)}
        assert with_surface & GATED
        assert not (without & GATED)
        # Everything that is not gated is unchanged.
        assert with_surface - GATED == without - GATED

    def test_the_default_keeps_the_old_behaviour(self):
        """Every existing caller and unit test must be unaffected."""
        source = TextSource(field_path="manifest.description", text=PROSE)
        assert {f.pattern_id for f in scan_text(source, set())} & GATED


class TestSurfaceStillJudged:
    """The regression guard: a real manifest is judged exactly as before."""

    def test_gated_detectors_still_fire_with_a_surface(self):
        result = scan_injection(_declaring_skill())
        assert result.pattern_ids & GATED, result.pattern_ids

    def test_a_declared_host_is_still_forgiven(self):
        """The pre-existing carve-out survives: honesty is not punished."""
        manifest = _declaring_skill()
        manifest.permissions = ["network:api.vendor.example"]
        assert "exfiltration" not in scan_injection(manifest).pattern_ids


class TestPoisonedStillCaught:
    """The gate that must never drop, run against the committed corpus."""

    @pytest.fixture(scope="class")
    @staticmethod
    def corpus() -> Corpus:
        return Corpus(CORPUS_DIR)

    def test_every_poisoned_fixture_is_still_dangerous(self, corpus):
        checked = 0
        for entry in corpus.load():
            if not entry.is_poisoned:
                continue
            report = audit_normalized(corpus.normalized(entry), skip_sandbox=True)
            assert report.final_verdict == FinalVerdict.DANGEROUS, entry.skill_id
            checked += 1
        assert checked >= 4

    def test_the_two_markdown_poisoned_fixtures_have_no_surface_either(self, corpus):
        """This is what makes the fix load-bearing rather than convenient.

        `markdown-linter` and `pdf-summarizer` are `agent-skill`, `tools=0`,
        `permissions=0` — indistinguishable from a catalog entry by shape. They are
        caught by the directive detectors, which is the right reason.
        """
        bare = []
        for entry in corpus.load():
            if not entry.is_poisoned:
                continue
            manifest = corpus.normalized(entry).manifest
            if not has_declaration_surface(manifest):
                bare.append(entry.skill_id)
        assert len(bare) >= 2, "expected the markdown poisoned fixtures to have no surface"

    def test_poisoned_markdown_is_caught_by_directive_detectors(self, corpus):
        directive = {
            "ignore_instructions", "html_comment_directive",
            "credential_path", "wallet_op", "hidden_block", "zero_width",
        }
        for entry in corpus.load():
            if not entry.is_poisoned:
                continue
            normalized = corpus.normalized(entry)
            if has_declaration_surface(normalized.manifest):
                continue
            report = audit_normalized(normalized, skip_sandbox=True)
            fired = {f.pattern_id for f in report.stage1.injection_findings}
            assert fired & directive, f"{entry.skill_id} caught only by gated detectors"


class TestCatalogAfterTheFix:
    """What STE-18 can now stand behind."""

    @pytest.fixture(scope="class")
    @staticmethod
    def verdicts() -> dict[str, FinalVerdict]:
        corpus = Corpus(CORPUS_DIR)
        return {
            e.skill_id: audit_normalized(corpus.normalized(e), skip_sandbox=True).final_verdict
            for e in corpus.load()
            if e.label == "catalog"
        }

    def test_axelar_is_no_longer_accused(self, verdicts):
        assert verdicts["org.stellar.skills.cross-chain.axelar"] == FinalVerdict.SAFE

    def test_at_least_twelve_catalog_skills_are_safe(self, verdicts):
        """SOW D2 wants 10+ real catalog skills; this is the pool STE-18 can seed."""
        safe = [k for k, v in verdicts.items() if v == FinalVerdict.SAFE]
        assert len(safe) >= 12, sorted(k for k, v in verdicts.items() if v != FinalVerdict.SAFE)

    def test_cctp_is_still_flagged_and_that_is_known(self, verdicts):
        """Not fixed here on purpose.

        cctp's prose describes a protocol that burns and mints USDC, and `wallet_op`
        reads that as an instruction to move assets. Same family as the
        `com.fixtures.safe.price-checker` false positive. `wallet_op` is a critical-class
        detector protecting `token-drainer` and `invoice-helper`, so relaxing it to make
        one entry green is exactly what corpus/README.md warns against. Pinned so that
        fixing it properly makes this test fail and forces the entry to be removed.
        """
        assert verdicts["org.stellar.skills.cross-chain.cctp"] == FinalVerdict.DANGEROUS

    def test_no_catalog_entry_is_flagged_by_a_gated_detector_alone(self):
        """The remaining flag must be a real directive finding, not a category error."""
        corpus = Corpus(CORPUS_DIR)
        for entry in corpus.load():
            if entry.label != "catalog":
                continue
            report = audit_normalized(corpus.normalized(entry), skip_sandbox=True)
            fired = {f.pattern_id for f in report.stage1.injection_findings}
            assert not (fired & GATED), f"{entry.skill_id} still trips {fired & GATED}"
