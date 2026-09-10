# Sterish audit corpus

The set of skills the audit pipeline is exercised against, as byte-exact
snapshots plus a provenance index. It backs the STERISH-14 seed run and the
SOW D2 evidence ("10+ real catalog skills audited").

## What's here

| Group | Count | Source |
|---|---|---|
| `catalog/` | 13 | Real skills fetched from [skills.stellar.org](https://skills.stellar.org) |
| `fixtures/*` (poisoned) | 4 | Authored attacks — description-injection, hidden HTML comment, MCP auto-approve smuggling, declared wallet/secret drain |
| `fixtures/*` (safe) | 3 | Authored legitimate skills that must audit clean |

`index.json` is the manifest: one entry per skill with its `content_hash`, the
digest of every file, provenance (source URL, fetch time, upstream ETag), and —
for fixtures — the `expected_verdict`.

## Reproduce it

```bash
cd pipeline

# Recompute every hash from the snapshot bytes; nonzero exit on any drift.
uv run python -m sterish_pipeline.cli intake verify --corpus corpus

# Audit the whole corpus in one deterministic, offline run (no API key).
uv run python -m sterish_pipeline.cli intake audit-corpus --corpus corpus --strict
```

`--strict` fails if any fixture misses its `expected_verdict`. Independently of
`--strict`, a **poisoned fixture that audits as SAFE is always a hard failure** —
that is the guarantee the corpus exists to defend.

### `--strict` currently exits non-zero, on purpose

You will see exactly one mismatch:

```
! com.fixtures.safe.price-checker: expected SAFE, got DANGEROUS
```

That is a real false positive and it is left visible rather than hidden. The
`wallet_op` detector is deliberately negation-blind (documented in
`stages/injection_rules.py`), so the sentence *"it never touches a wallet, never
signs anything, never moves funds"* grades the skill DANGEROUS. Editing the
fixture or relaxing its expected verdict would make the run green and the
scanner no better, so neither was done. `tests/test_corpus.py` asserts this set
**exactly**, which means fixing the scanner breaks that test and forces the entry
to be removed.

`org.stellar.skills.cross-chain.cctp` fails for the same reason but does not show
up here, because catalog entries carry no `expected_verdict` to miss. See below.

## Rebuild it

```bash
cd pipeline
uv run python -m sterish_pipeline.cli intake fetch --corpus corpus   # catalog (network)
uv run python scripts/build_fixture_corpus.py                         # fixtures
```

Snapshots are committed rather than fetched at audit time so their
`content_hash` is stable: an audit whose subject can change under it proves
nothing. The bytes are marked `-text` in `.gitattributes` so git never rewrites
their line endings.

## A note on the poisoned fixtures

`fixtures/poisoned-*`, `fixtures/evil-mcp`, and `fixtures/token-drainer-mcp`
contain deliberately malicious instruction text. They are inert test data — the
pipeline's job is to flag them DANGEROUS — not runnable programs. Do not lift
their contents into a real skill.

## Reading the catalog verdicts (important)

The 13 `org.stellar.skills.*` entries carry no `permissions` and no `tools`. That
is not a defect in the snapshot: an Agent Skill published as markdown *is* the
skill. An agent loads `axelar.md` into its context and follows it, and the format
has nowhere to declare a permission. Calling them "documentation, not real skills"
is the wrong read — and this file used to make it.

The risk surface of a prose skill is therefore prompt injection in the prose, and
that is exactly what the directive detectors look for.

**Fixed in STE-36.** `exfiltration` and `undeclared_capability` work by comparing
prose against `manifest.permissions` / `manifest.tools`. With nothing declared they
compared against an empty set and fired on every URL and every descriptive
sentence, so `axelar` and `cctp` came back DANGEROUS for, among other things,
citing `docs.axelar.dev` in a markdown link. Both detectors are now gated on the
manifest having a declaration surface at all; the directive detectors are
untouched, which is why all four poisoned fixtures are still caught.

After the fix, 12 of 13 catalog entries audit `SAFE`. The exception:

* **`org.stellar.skills.cross-chain.cctp` is still `DANGEROUS`, and it is still
  wrong.** Its prose explains that CCTP burns USDC on one chain and mints it on
  another; `wallet_op` reads that as an instruction to move assets. Same family as
  the `com.fixtures.safe.price-checker` false positive below. `wallet_op` is a
  critical-class detector protecting `token-drainer` and `invoice-helper`, so
  relaxing it to turn one entry green is the papering-over this file warns about
  further down. Tracked separately; **`cctp` is held out of the on-chain seed run
  rather than published as a false accusation.**

`expected_verdict` stays `null` for catalog entries in `index.json`, because the
corpus should not hard-code a claim about bytes it does not own. The assertions
that do exist live in `tests/test_declaration_surface.py`, which pins that the
poisoned fixtures stay `DANGEROUS`, that no catalog entry is flagged by a gated
detector any more, and that `cctp` is still flagged — so fixing `wallet_op`
properly makes that last test fail and forces this note to be revisited.

The fixtures under `corpus/fixtures/` carry real `expected_verdict` values,
because they are authored here and their bytes are ours.
