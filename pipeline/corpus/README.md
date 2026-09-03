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
uv run python -m sterish_pipeline.cli audit-corpus --corpus corpus --strict
```

`--strict` fails if any fixture misses its `expected_verdict`. Independently of
`--strict`, a **poisoned fixture that audits as SAFE is always a hard failure** —
that is the guarantee the corpus exists to defend.

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
