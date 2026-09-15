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

### `--strict` exits zero since STE-37

Until STE-37 it failed on exactly one mismatch, `com.fixtures.safe.price-checker:
expected SAFE, got DANGEROUS`. That was a real false positive, left visible rather
than hidden: `wallet_op` was negation-blind, so *"it never touches a wallet, never
signs anything, never moves funds"* graded the skill DANGEROUS. The fixture and its
expected verdict were never edited to make the run green; the scanner was fixed
instead (`wallet_op` now reads whether a sentence directs a move — see
`stages/injection_rules.py`, "wallet_op reads context"). `tests/test_corpus.py`
still asserts the mismatch set exactly, and it is now empty.

Measured on the whole corpus after the fix: **0 false positives out of 16 benign
entries, 0 false negatives out of 4 poisoned ones** (`tests/test_wallet_op_context.py`).

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

After STE-36, 12 of 13 catalog entries audited `SAFE`. The exception was
`org.stellar.skills.cross-chain.cctp`: its prose explains that CCTP burns USDC on
one chain and mints it on another, and a negation- and context-blind `wallet_op`
read that as an instruction to move assets. It was held out of the on-chain seed
run rather than published as a false accusation.

**Fixed in STE-37: all 13 catalog entries audit `SAFE`.** `wallet_op` now fires only
on a sentence that *directs* a move — an instruction aimed at the agent, or assets
moved to a party or out of someone else's hands — and not on a denial, a protocol
name, or a description of what a protocol does. It was not simply loosened: every
phrasing in the poisoned fixtures still fires, including attempts to hide an
instruction next to a denial, and `token-drainer` and `invoice-helper` are still
caught by `wallet_op` itself (`tests/test_wallet_op_context.py`).

Publishing `cctp` on chain, and correcting the `DANGEROUS` verdict
`com.fixtures.safe.price-checker` already carries on testnet, is a seed-run
decision (STE-18), not part of the scanner fix.

`expected_verdict` stays `null` for catalog entries in `index.json`, because the
corpus should not hard-code a claim about bytes it does not own. The assertions
that do exist live in `tests/test_declaration_surface.py`, which pins that the
poisoned fixtures stay `DANGEROUS`, that no catalog entry is flagged by a gated
detector any more, and that `cctp` audits `SAFE`.

The fixtures under `corpus/fixtures/` carry real `expected_verdict` values,
because they are authored here and their bytes are ours.
