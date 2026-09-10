# Sterish — Frozen Specs

The handoff contract between owners. Once the documents in this folder are merged, James and
Ancung can build in parallel without waiting for anyone's implementation to be finished — for
as long as everyone abides by what is in here.

**Status: FROZEN v1.1.0** (STE-11, 2026-09-03).

---

## Contents

| Document | What it freezes | Used by |
|---|---|---|
| [`content-hash.md`](content-hash.md) | Canonical bytes v1 and `content_hash = sha256(...)`, byte-exact | pipeline (intake), contracts (`lookup_by_hash`), dashboard (check-before-install) |
| [`interfaces.md`](interfaces.md) | Every public function signature of Registry, Escrow and Tokens | everyone |
| [`events.md`](events.md) | Every `#[contractevent]` layout including which fields become topics (10 events) | indexer, API, dashboard |
| [`verdict-json.md`](verdict-json.md) + [`verdict.schema.json`](verdict.schema.json) | The verdict JSON schema the pipeline emits | stage 3, the on-chain submitter, API, dashboard |
| [`../api-spec.md`](../api-spec.md) | API response shapes, including check-by-`content_hash` and the evidence links | dashboard, calling agents |
| [`vectors/`](vectors/) | `content_hash` test vectors (plus error cases) | all three implementations |
| [`reference/`](reference/) | Reference `content_hash` implementations (Python and TypeScript) | pipeline, dashboard |
| [`examples/`](examples/) | Valid and invalid verdict JSON examples | stage 3, submitter, API |

The Rust side lives as a test in `contracts/registry/src/test.rs` and hashes through
`env.crypto().sha256()` — the same host function the deployed contract uses.

---

## How to verify it (anyone, no special access)

```bash
make verify-spec
# or one at a time:
bash scripts/verify-content-hash.sh    # identical hashes in Python + TypeScript + Rust
bash scripts/verify-verdict-json.sh    # example verdicts pass/fail against the schema
bash scripts/verify-soulbound.sh       # the tokens contract spec has no transfer/approve/burn
```

The runner executes **three** implementations (Python, TypeScript, Rust), `diff`s their reports
byte for byte, then checks the relationships between vectors. A non-zero exit code means at
least one of them diverged. The runner has been negative-tested: changing one byte in a fixture,
or hand-editing an `expected_sha256`, makes it fail.

> **Third-party reproducibility evidence.** Beyond the three implementations in this repository,
> the PM wrote a fourth from scratch — working only from the text of `content-hash.md`, without
> looking at `reference/` — and got all eight hashes identical. If the spec were ambiguous, that
> could not have happened.

---

## Change process (MANDATORY)

The specs in this folder are **frozen**. Any change to an interface, an event layout,
`content_hash`, the verdict JSON schema, or an API response shape must:

1. **Go through a new PR**, never straight to `main`.
2. **Be approved by Axel (PM) and fable (AI co-PM)** — both, not either.
3. **Be recorded in the changelog** below, with the date, the PR, and the reason.
4. **Reach the affected owners** (James: pipeline/API/indexer; Ancung: dashboard) *before* the
   merge, not after.

### Versioning rules

- `content_hash`: the algorithm is **immutable**. Changing a canonicalization rule produces a
  **new** algorithm (`sterish-content-hash/v2\n` as the MAGIC), not an edit to v1. Old hashes
  must remain recomputable forever; otherwise every verdict already written on chain becomes
  unverifiable.
- **Contract error codes** (`RegistryError` 1–9, `EscrowError` 1–9, `TokenError` 1–6) are public
  ABI. Variants may be **added** at the next number; they may **not** be renumbered or removed.
- **Events**: adding a new event is additive and safe. Changing the fields or topics of an
  existing one is breaking, and must go through the rules above.

---

## Changelog

### v1.1.0 — 2026-09-03 (STE-11, PR TBD)

Additive. Nothing from v1.0.0 changed shape.

- **§5 of `interfaces.md` moves from `PLANNED` to FROZEN**: the `sterish_tokens` contract (the
  VERIFIED badge and the licence token, both soulbound) now has a generated ABI, a function
  table, invariants T1–T7, and public `TokenError` codes 1–6.
- **`events.md` §3b**: two new events, `verified_minted` and `license_minted`, plus their
  emission-order rows.
- The three open questions in the old §5.3 are answered and recorded in §5.5: a licence is bound
  to `(skill_id, version)` rather than `content_hash`, royalties are **dropped** (a soulbound
  token has no resale), and `mint_license` is called by a single `MinterRole` the admin can
  rotate.

Decisions that differ from the wording of ticket STE-11, and why:

- **No OpenZeppelin.** `stellar-tokens` 0.7.2 requires `soroban-sdk ^26.1.0` while the workspace
  is frozen at `27.0.6` — cargo resolves two incompatible copies of the SDK. Independently of
  that, OZ 0.7.2's `non_fungible` module **has no soulbound support**: `contractimpl`-ing the
  `NonFungibleToken` trait exports exactly the `transfer`/`approve` the ticket forbids. A custom
  contract is the only way to satisfy the frozen stack *and* the soulbound done-criteria at once.
- **`mint_verified(skill_id, version, owner)`** takes `owner` as a parameter rather than reading
  it from the Registry — reading it would require duplicating the `SkillEntry` struct inside the
  tokens crate, which creates drift against the frozen ABI. The `Safe` verdict is still checked
  on chain, and that is the part that matters.
- **`mint_license` checks the Registry live**, not just the local badge. The badge is a snapshot
  taken at mint time and cannot be burned (soulbound), so without this check a version
  re-audited as `Dangerous` could keep selling licences through a stale badge. Licences already
  sold remain valid.
- **`TokenError::NotAuthorized` was removed** before the freeze (a dead variant — every role
  check fails through `require_auth()` as a host error). After this freeze the error codes are
  public ABI.

Known limits, left deliberately:

- **A badge cannot be revoked** (invariant T7). Without `burn`, `is_verified_token` can remain
  `true` after a version is re-audited `Dangerous`. A consumer that needs a live answer MUST
  read `SkillRegistry::is_verified`. The dangerous path — selling new licences — is closed.


### v1.0.0 — 2026-09-03 (STE-10, PR TBD)

The initial freeze. Built on top of already-merged contracts: STE-5 (Registry) and STE-9
(Escrow).

Decisions taken outside of, or differently from, the ticket's recommendations, and why:

- **No JSON canonicalization.** The ticket recommended a "normalised manifest JSON (sorted
  keys)". Rejected: canonicalizing JSON across Rust, Python and TypeScript — float formatting,
  key order, escaping, large integers — is a larger source of drift than the problem it solves.
  `manifest.json` is treated as ordinary bytes, like every other file.
- **File ordering is bytewise on the UTF-8 path**, not string comparison. The reason is that
  JavaScript's `Array.prototype.sort()` orders by UTF-16 code unit, which differs for non-BMP
  characters. The `non-bmp-path-order` vector exists specifically to catch that mistake.
- **A `u32be` length prefix on both path and content**, so that `("ab","c")` and `("a","bc")`
  can never produce the same byte stream. The `concat-ambiguity-a/b` vectors prove it.
- **Normalisation is CRLF→LF plus stripping a trailing newline, and nothing else.** No per-line
  trimming, no Unicode normalisation. Every additional normalisation enlarges the surface where
  a change can hide; CRLF and a trailing newline cannot carry a payload.
- **Files must be valid UTF-8**; binary files are rejected (`NotUtf8`). A known v1 limit — a
  skill shipping binary assets needs v2.
- **Backslashes are rejected in paths.** Legal on POSIX, rejected on purpose so that
  `tools\zeta.py` from a Windows packager is not silently read as a single filename.
- **Verdict JSON gains 3 identity fields** beyond the ticket's list: `skill_id`, `version`,
  `content_hash`. Without them the on-chain submitter does not know which record to write.
- **8 test vectors**, where the ticket asked for at least 3.

Known limits, left deliberately:

- The exclusion list (`.git/**`, `node_modules/**`, and so on) currently lives only in the
  reference implementations. The pipeline (STE-13) **must use `hash_dir()` from
  `reference/content_hash.py`** rather than writing its own packager — otherwise the drift comes
  back through the side door.
- The VERIFIED/licence token interface is marked `STATUS: PLANNED` and is not yet frozen; it
  follows in STE-11.
