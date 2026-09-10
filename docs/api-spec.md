# Sterish — Verification API Specification (v1, frozen)

> REST API that answers one question for an agent about to install a skill:
> **"are these exact bytes audited, and what was the verdict?"**

| | |
|---|---|
| Spec version | `1.0.0` |
| Frozen at | STE-10 |
| Reads from | `sterish_registry` on Soroban, via Stellar RPC |
| Companion specs | [`specs/interfaces.md`](./specs/interfaces.md), [`specs/events.md`](./specs/events.md), [`specs/verdict-json.md`](./specs/verdict-json.md), [`specs/content-hash.md`](./specs/content-hash.md) |
| Base URL (dev) | `http://localhost:8000` |

## 0. What changed in this revision, and why

The previous version of this file described an API that **cannot be built against the merged
contracts**. STE-5 moved the verdict from the skill header to the version record; this file had
not caught up.

| # | Old spec said | Reality in `contracts/registry` | Fix |
|---|---|---|---|
| A1 | `GET /check/{skill_id}` returns one `verdict` for the skill | `SkillEntry` has **no** `latest_verdict` field. Verdict lives on `VersionRecord`, per version. Auditing v1 says nothing about v2 — that inheritance was the scaffold bug STE-5 removed. | A skill-level endpoint no longer returns a verdict at all. Verdicts are only served per version, or by content hash. |
| A2 | `GET /skills` items carry `verdict` + `trust_score` at skill level | same as A1 | List items carry `latest_version` / `latest_audited_version` pointers and a per-version verdict for the audited one, explicitly labelled. |
| A3 | No way to ask about bytes | `lookup_by_hash(content_hash) -> Option<VersionRecord>` is the contract's primary read path and the whole point of content-hash pinning | **New `GET /check/by-hash/{content_hash}`**, and it is now the recommended endpoint. |
| A4 | `evidence` was a bare string, sometimes empty | on-chain there is `evidence_hash: BytesN<32>`; there is no `report_uri` on-chain (see `interfaces.md` §6 D3) | Every response now carries a structured `evidence` object with the transaction links, the on-chain `evidence_hash`, and the API-served `report_uri`. |
| A5 | `audit_timestamp` as an ISO string | on-chain `audited_at` is a `u64` ledger timestamp | Both are served: `audited_at` (integer, authoritative) and `audited_at_iso` (convenience). |
| A6 | verdict enum listed as `UNAUDITED, SAFE, DANGEROUS, WARNING` | correct, and matches `AuditVerdict` | Unchanged — but `UNAUDITED` now has a documented meaning per version, and the API must never render it as "safe". |

### Implementation status

**Implemented in STE-17** (2026-09-04) and serving live chain reads against the STE-13
testnet deployment. Every section here is implemented.

| Section | Status |
|---|---|
| 3.1 `GET /check/by-hash/{content_hash}` | implemented |
| 3.2 `GET /check/{skill_id}/{version}` | implemented |
| 3.3 `GET /skills/{skill_id}` | implemented |
| 3.4 `GET /skills` | implemented |
| 3.5 `GET /health` | implemented |
| 3.6 `GET /reports/{skill_id}/{version}` | implemented (STE-32) — `report_uri` is advertised only when a base URL is set **and** the report exists |
| 3.7 `GET /use/{skill_id}/{version}` | implemented (STE-19) |
| 3.8 `GET /license/{skill_id}/{version}` | implemented (STE-35) |
| 3.9 `GET /feed` | implemented (STE-17) — was live but undocumented until STE-35 |

What the scaffold had, and what replaced it:

- `client.py::_mock_skills` returned mock data unconditionally — even with a contract
  deployed, because the `TODO` branch and the fallback branch were the same line. The
  module is deleted; `chain.py` reads the contract over Stellar RPC.
- `routes/check.py` imported `SkillListItem` from a module that does not exist, so the
  package could not even be imported. Rewritten against the models in this spec.
- Transaction hashes now come from `indexer.py`, which tails `skill_registered`,
  `version_registered`, `version_recorded` and `verdict_flipped` into SQLite.

Two behaviours worth stating because they were found empirically against testnet rather
than read from documentation:

- **`getEvents` scans only a bounded window forward from `start_ledger`.** A start 5 000
  ledgers before a known event still returned it; 10 000 before returned nothing, with no
  error. Asking once for the whole retained range silently yields zero events, so the
  indexer walks forward in `INDEXER_CHUNK_LEDGERS` steps.
- **A contract `Err(...)` arrives as text, not an exception.** It surfaces in
  `simulateTransaction`'s `error` field as `Error(Contract, #N)`, which is what the
  mapping in section 4 parses.

Verified end-to-end against testnet: the poisoned fixture reads back `DANGEROUS`, the safe
fixture reads back `SAFE`, and flipping one byte of a registered hash returns `404`.

---

## 1. Design rules (frozen)

1. **The unit of truth is `(skill_id, version)`, or better, `content_hash`.** No endpoint ever
   returns a verdict keyed on `skill_id` alone.
2. **Every response that carries a verdict carries evidence.** A verdict without a link to the
   transaction that wrote it is an unverifiable claim, which is exactly what this project
   exists to eliminate. See §2.
3. **A miss is a `404`, never a fabricated "unknown but probably fine".** `lookup_by_hash`
   returning `None` means the bytes are not registered — the API says so plainly.
4. **`UNAUDITED` is not a soft `SAFE`.** It is rendered as its own state with
   `is_verified: false`.
5. **`is_verified` is `true` only for `verdict == "SAFE"` on that exact version.** It mirrors
   the contract's `is_verified` and is the only field a client should gate an install on.
6. **All reads are unauthenticated.** Everything served is public ledger data.

---

## 2. The `evidence` object (shared by every verdict-bearing response)

```json
{
  "evidence": {
    "registry_contract_id": "CDLZ...ABCD",
    "contract_url": "https://stellar.expert/explorer/testnet/contract/CDLZ...ABCD",
    "registration_tx": "3f8b...c1",
    "registration_tx_url": "https://stellar.expert/explorer/testnet/tx/3f8b...c1",
    "audit_tx": "9ac2...7e",
    "audit_tx_url": "https://stellar.expert/explorer/testnet/tx/9ac2...7e",
    "evidence_hash": "34a5eae5969fb0e2f6856c17a58066e81825cd254f3142c55d93caf58c5a324f",
    "report_uri": "https://api.sterish.dev/reports/com.evil.token-drainer/1.0.0.json"
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `registry_contract_id` | string | The `C…` address the answer was read from. Lets a client verify independently. |
| `contract_url` | string | stellar.expert link for that contract. |
| `registration_tx` / `_url` | string \| null | Transaction that emitted `version_registered` for this version. |
| `audit_tx` / `_url` | string \| null | Transaction that emitted `version_recorded`. `null` while the version is `UNAUDITED`. |
| `evidence_hash` | 64 hex \| null | `VersionRecord.evidence_hash`, read from the chain. All-zero on-chain while unaudited; served as `null` in that case. |
| `report_uri` | string \| null | Where the full verdict JSON (`specs/verdict-json.md`) is served. **Off-chain and mutable** — a client MUST fetch it and check `sha256(bytes) == evidence_hash` before trusting it. There is deliberately no `report_uri` on-chain. |

Explorer base URL is network-dependent: `https://stellar.expert/explorer/testnet/...` on
testnet, `.../public/...` on mainnet. The API derives it from its configured network passphrase
and must never hardcode one.

Transaction hashes come from the indexer (STE-13), not from contract state — the contract does
not store them. Until the indexer exists, the tx fields are served as `null` and the rest of
the `evidence` object is still populated. **They must never be omitted or faked.**

---

## 3. Endpoints

### 3.1 `GET /check/by-hash/{content_hash}` — the primary path

Answers "are *these bytes* audited?". The client computes `content_hash` locally over the
skill it is about to install (canonical bytes v1, `specs/content-hash.md`) and asks. This is
the endpoint that makes a poisoned v2 unable to inherit v1's badge: a single changed byte
produces a different hash, which misses.

**Path parameters**

| Parameter | Type | Notes |
|---|---|---|
| `content_hash` | string | Exactly 64 lowercase hex characters. Uppercase is rejected with `400`, not silently normalized — a client that produced uppercase has a bug worth surfacing. |

Backed by `lookup_by_hash(content_hash) -> Option<VersionRecord>` (one RPC simulate call).

**200 — bytes are registered**

```json
{
  "skill_id": "com.evil.token-drainer",
  "version": "1.0.0",
  "content_hash": "c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0",
  "verdict": "DANGEROUS",
  "trust_score": 5,
  "is_verified": false,
  "owner": "GBRP...X4",
  "auditor": "GCBY...QK",
  "registered_at": 1756890000,
  "audited_at": 1756893600,
  "audited_at_iso": "2025-09-03T09:20:00Z",
  "evidence": { "...": "see §2" }
}
```

| Field | Type | Notes |
|---|---|---|
| `skill_id`, `version` | string | Resolved from the hash index; unambiguous by invariant R3. |
| `content_hash` | 64 hex | Echoed back so a client can assert it asked about what it thinks it asked about. |
| `verdict` | enum | `SAFE` \| `DANGEROUS` \| `WARNING` \| `UNAUDITED`. |
| `trust_score` | integer 0–100 | `0` while unaudited. |
| `is_verified` | boolean | `verdict == "SAFE"`. **The only field to gate an install on.** |
| `owner` | string | `G…` address that registered the version. |
| `auditor` | string \| null | `null` while unaudited. |
| `registered_at` | integer | Ledger timestamp (unix seconds). |
| `audited_at` | integer \| null | `null` (not `0`) while unaudited. |
| `audited_at_iso` | string \| null | Convenience rendering of `audited_at`. |

**404 — bytes are unknown**

```json
{
  "error": "NOT_FOUND",
  "detail": "content_hash c2bd4a...87f0 is not registered",
  "content_hash": "c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0",
  "is_verified": false
}
```

`is_verified: false` is included in the 404 body on purpose: a client that only reads that one
field cannot accidentally treat "unknown" as anything but unverified.

**400** — `content_hash` is not 64 lowercase hex characters.

### 3.2 `GET /check/{skill_id}/{version}`

Same response body as §3.1, resolved by name instead of by bytes. Backed by
`get_version(skill_id, version)`.

Use this for display. **Prefer §3.1 for a security decision**, because asking by name trusts
the name, while asking by hash trusts nothing.

**404** — `SkillNotFound`(3) or `VersionNotFound`(4). The body distinguishes them:

```json
{ "error": "VERSION_NOT_FOUND", "detail": "skill 'com.acme.pdf-suite' has no version '9.9.9'" }
```

### 3.3 `GET /skills/{skill_id}`

Skill header. Backed by `query_skill(skill_id)`.

**There is no `verdict` field on this response, at any level, by design (A1).**

```json
{
  "skill_id": "com.acme.pdf-suite",
  "owner": "GBRP...X4",
  "registered_at": 1756800000,
  "versions": ["0.9.0", "0.9.3"],
  "latest_version": "0.9.3",
  "latest_audited_version": "0.9.0",
  "audited_versions": [
    {
      "version": "0.9.0",
      "content_hash": "a67ded...0d5e",
      "verdict": "SAFE",
      "trust_score": 88,
      "is_verified": true,
      "audited_at": 1756810000,
      "evidence": { "...": "see §2" }
    }
  ],
  "warning": "latest_version 0.9.3 is NOT the audited version. A verdict applies to one version only."
}
```

| Field | Type | Notes |
|---|---|---|
| `versions` | array of string | Every registered version, in registration order. |
| `latest_version` | string | Last **registered**. Says nothing about audits. |
| `latest_audited_version` | string \| null | Last version that received a verdict. `null` if none ever was. |
| `audited_versions` | array | Per-version records for versions with a verdict; each carries its own `evidence`. |
| `warning` | string \| null | Present **only** when `latest_version != latest_audited_version`. This is the exact confusion the old spec encouraged, so the API names it out loud. |

Cost note: filling `audited_versions` needs one `get_version` call per version. The API caps
this (see §6) and, once the indexer (STE-13) exists, serves it from the index instead.

### 3.4 `GET /skills`

Paginated catalogue. Backed by `query_all_skills(start, limit)`.

**Query parameters**

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `start` | integer ≥ 0 | `0` | Offset into the registration-order index. |
| `limit` | integer 1–100 | `20` | Clamped to 100. |

```json
{
  "skills": [
    {
      "skill_id": "com.acme.pdf-suite",
      "owner": "GBRP...X4",
      "registered_at": 1756800000,
      "version_count": 2,
      "latest_version": "0.9.3",
      "latest_audited_version": "0.9.0",
      "latest_audited_verdict": "SAFE",
      "latest_audited_trust_score": 88,
      "latest_audited_is_verified": true
    }
  ],
  "total": 42,
  "start": 0,
  "limit": 20
}
```

The verdict fields are prefixed `latest_audited_` rather than being bare `verdict` /
`trust_score`. Verbose on purpose: a bare `verdict` on a list row is what let a UI show a badge
next to a skill whose newest version was never audited. `total` comes from `get_skill_count()`.

### 3.5 `GET /health`

```json
{ "status": "ok", "version": "0.1.0", "network": "testnet",
  "registry_contract_id": "CDLZ...ABCD", "rpc_url": "https://soroban-testnet.stellar.org",
  "rpc_reachable": true, "indexer_lag_ledgers": null }
```

Returns `200` when the process is up and `503` when `rpc_reachable` is `false` — a health check
that reports `ok` while the API cannot read the chain is worse than no health check.
`indexer_lag_ledgers` is `null` until STE-13 lands.

### 3.6 `GET /reports/{skill_id}/{version}` — the report `evidence_hash` commits to (STE-32)

Serves the full verdict JSON (`specs/verdict-json.md`). This is the last link of the
verification chain: `evidence_hash` on chain is the sha256 of exactly these bytes, so a caller
can recompute it and check a verdict without trusting us.

```json
{ "spec_version": "1.0.0", "skill_id": "…", "version": "…", "content_hash": "…",
  "verdict": "DANGEROUS", "risk": "critical", "score": 10,
  "capabilities": ["SECRET_READ"],
  "findings": [{"stage": 1, "severity": "HIGH",
                "description": "[credential_path] Text references credential material.",
                "evidence": "SKILL.md: \"...read the user's ~/.ssh/id_rsa...\""}],
  "recommendation": "BLOCK", "evidence_hash": "…" }
```

`findings`, `capabilities` and `recommendation` are the fields §6 of `verdict-json.md` keeps
off-chain; this endpoint is the only way to read them, which is why a verdict could previously
say DANGEROUS but never say why.

**The bytes are served exactly as they were hashed** — not re-serialised on the way out.
Round-tripping the document through a JSON encoder makes the digest depend on separator and
key-order choices, which is how this kind of check quietly stops matching. The response
carries `X-STERISH-EVIDENCE-HASH` so a client can check our arithmetic without a second
round trip to the chain.

**A mismatch is never a `200`.** If the bytes on disk do not hash to what the chain recorded,
one of the two has changed since the audit and the response is `500 REPORT_HASH_MISMATCH`,
naming both digests. Serving tampered evidence under a reassuring status code is the one
outcome this endpoint exists to prevent.

`report_uri` in the `evidence` object (§2) points here. It is advertised only when a base URL
is configured **and** the report for that version actually exists, so a client is never handed
a link that 404s — the reason this section stayed `PLANNED` rather than shipping a dead URL.

**Errors:** `404 REPORT_NOT_FOUND` (never an empty object — "no report" and "a report finding
nothing" are different answers), `409 NO_EVIDENCE_ANCHOR` (registered but never audited, so
there is nothing to verify against), `500 REPORT_HASH_MISMATCH`, `503 NOT_CONFIGURED`
(`STERISH_REPORTS_DIR` unset).

### 3.7 `GET /use/{skill_id}/{version}` — the paid path (STE-19)

Implemented. `GET`, not `POST`: the request is a read of a licensed artifact, and x402 clients
negotiate on the same verb they retry with.

Three outcomes, checked in this order:

| Condition | Response |
|---|---|
| caller holds a licence for this exact version | `200` + artifact, `X-STERISH-LICENSE: held` |
| no licence, no payment | `402` + `PAYMENT-REQUIRED` header, empty body |
| no licence, `X-PAYMENT` attached | verify → settle → mint → `200`, `X-STERISH-LICENSE: minted` |

A version the registry did not call `SAFE` returns `403 NOT_VERIFIED` and is never offered for
sale. The tokens contract enforces this too (`mint_license` is gated on the VERIFIED badge), so
the check is defence in depth and a clearer error than a contract revert.

**Identifying the caller.** Before a payment exists there is nothing to derive an address from,
so a client that wants the "already licensed" shortcut sends `X-AGENT-ADDRESS: G…` (or `?agent=`).
After payment the payer is taken from the payment payload itself.

**The 402 body.** Requirements travel in the `PAYMENT-REQUIRED` header as base64 JSON, with an
empty body. This shape was captured from the reference `@x402/express` server against the same
facilitator, not inferred:

```json
{"x402Version": 2, "error": "Payment required",
 "resource": {"url": "…", "description": "License for <skill>@<version>", "mimeType": "application/json"},
 "accepts": [{"scheme": "exact", "network": "stellar:testnet",
              "amount": "1000000", "asset": "CBIELTK6…", "payTo": "GD73M4F7…",
              "maxTimeoutSeconds": 300, "extra": {"areFeesSponsored": true}}]}
```

`amount` is in 7-decimal base units — `1000000` is 0.10 USDC. **`payTo` is a classic `G…`
account** that receives the USDC and needs a USDC trustline; **`asset` is the SAC `C…` contract**
the protocol invokes `transfer` on. Confusing the two is the documented common stumble, so they
come from separate settings and neither is derived from the other.

**Content pinning.** The bytes are re-hashed and compared with the `content_hash` the registry
holds for that version before they leave the process. A mismatch is `500 ARTIFACT_HASH_MISMATCH`,
never a `200` with the wrong bytes — a buyer must not pay for one artifact and receive another.

**Degradation.** The facilitator is a third party. If it is unreachable the response is
`503 FACILITATOR_UNAVAILABLE`, never `402`: telling a buyer who just paid that they did not
invites them to pay twice. Reads (`/check`, `/skills`) and existing licence holders are
unaffected, and `/health` reports `facilitator_reachable` separately from `rpc_reachable`.

Verify runs before settle deliberately: settling first would move money for a request that is
about to be refused.

**Errors:** `403 NOT_VERIFIED`, `400 INVALID_PAYMENT`, `402 PAYMENT_REJECTED` (carries the
facilitator's own reason), `503 FACILITATOR_UNAVAILABLE`, `404 ARTIFACT_NOT_FOUND`,
`500 ARTIFACT_HASH_MISMATCH`.

### 3.8 `GET /license/{skill_id}/{version}` — licence status without the artifact (STE-35)

Read-only mirror of `has_license(agent, skill_id, version)` on the tokens contract. Answers one
question and nothing else.

**Query parameters**

| Parameter | Type | Notes |
|---|---|---|
| `agent` | `G…` account address | Required. May instead be sent as `X-AGENT-ADDRESS`. The query parameter wins if both are present. |

```json
{
  "skill_id": "com.acme.pdf-suite",
  "version": "1.0.0",
  "agent": "GD73M4F7…",
  "held": true,
  "tokens_contract_id": "CCHV…EJX",
  "contract_url": "https://stellar.expert/explorer/testnet/contract/CCHV…EJX"
}
```

Section 3.7 can already answer this — it checks the licence before offering to sell one — but it
answers by **serving the whole artifact**, so drawing one badge cost a full skill download and a
detail page with five versions cost five. It also answers wrongly in three ways this endpoint
does not:

| `GET /use` | `GET /license` |
|---|---|
| reads the artifact before replying, so a real licence still returns `404 ARTIFACT_NOT_FOUND` for any skill absent from `STERISH_SKILLS_DIR` | never touches the artifact directory |
| swallows a failed chain read and falls through to `402`, conflating "no licence" with "could not tell" | a failed read is `502 RPC_UNAVAILABLE`, never `held: false` |
| returns `403 NOT_VERIFIED` before looking at the licence, hiding existing holders of a version later re-audited to `DANGEROUS` | unconditional on the registry verdict |

That last row is deliberate and worth stating plainly: **this endpoint does not gate on the
verdict.** Holding a licence is a fact about the tokens contract alone. A caller that wants to
know whether a version is safe asks 3.1 or 3.2, which is a different read against a different
contract; conflating the two is what section 1's design rules exist to prevent.

A licence is pinned to one `(skill_id, version)` pair, so an unregistered skill and a
never-licensed one both answer `held: false` — that is the contract's own answer, not a guess.

**Errors:** `400 MISSING_AGENT`, `400 INVALID_AGENT` (not a `G…` account — contract `C…` and
muxed `M…` addresses are rejected rather than encoded into a read that would return `false` for
the wrong reason), `503 NOT_CONFIGURED`, `502 RPC_UNAVAILABLE`.

### 3.9 `GET /feed` — indexed registry activity

Registry events the indexer has tailed, newest first. Backed by SQLite, not by the chain.

**Query parameters**

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `limit` | integer 1–200 | `50` | |
| `offset` | integer ≥ 0 | `0` | |

```json
{
  "events": [
    {
      "event": "version_recorded",
      "skill_id": "com.acme.pdf-suite",
      "version": "1.0.0",
      "content_hash": "4bf3f90c…",
      "verdict": "SAFE",
      "trust_score": 88,
      "ledger": 4584943,
      "tx_hash": "499883165894078a…",
      "tx_url": "https://stellar.expert/explorer/testnet/tx/499883165894078a…",
      "occurred_at": 1756810000,
      "occurred_at_iso": "2026-09-03T11:48:57Z"
    }
  ],
  "total": 231,
  "indexer_enabled": true,
  "last_indexed_ledger": 4584943
}
```

`event` is one of `skill_registered`, `version_registered`, `version_recorded`, `verdict_flipped`.
`version`, `content_hash`, `verdict`, `trust_score` and the timestamps are null on events that do
not carry them — `skill_registered` has no version, for instance.

**This is a convenience feed, not a verdict source.** It is served from the index by definition,
and section 6 makes the index a cache that is never the source of truth. A client that wants a
verdict it can act on reads 3.1 or 3.2, which go to the chain on every request. The honest use
for this endpoint is "what happened recently, and where is the transaction" — the `tx_url` is the
part worth trusting, because it points at something a third party can verify independently.

`indexer_enabled` and `last_indexed_ledger` are returned so a caller can tell a genuinely quiet
registry from an indexer that is switched off or has fallen behind; with `INDEXER_ENABLED=0` the
feed is empty and `last_indexed_ledger` is null, which must not read as "nothing has happened".

---

## 4. Errors

All error responses share one shape:

```json
{ "error": "NOT_FOUND", "detail": "human-readable description" }
```

| Status | `error` | Cause | Registry error |
|---|---|---|---|
| 400 | `INVALID_CONTENT_HASH` | not 64 lowercase hex | — |
| 400 | `INVALID_PARAMETER` | bad `start` / `limit` / empty id | — |
| 404 | `NOT_FOUND` | `content_hash` not in the hash index | `lookup_by_hash` → `None` |
| 404 | `SKILL_NOT_FOUND` | unknown `skill_id` | `SkillNotFound` (3) |
| 404 | `VERSION_NOT_FOUND` | known skill, unknown version | `VersionNotFound` (4) |
| 502 | `RPC_UNAVAILABLE` | Stellar RPC unreachable or returned an error | — |
| 503 | `NOT_CONFIGURED` | `REGISTRY_CONTRACT_ID` unset | `NotInitialized` (1) |
| 500 | `INTERNAL` | anything else | — |

**A read failure is never a `200` with a default verdict.** If the API cannot reach the chain
it returns `502`. Serving a stale or invented "SAFE" is the single worst thing this service
could do.

The old `{"detail": "..."}`-only body is replaced by the `error` + `detail` pair, matching
`api/src/sterish_api/models.py::ErrorResponse`, which already has both fields.

---

## 5. Client flow: check before install

```
1. Fetch the skill artifact.
2. Compute content_hash locally  (specs/content-hash.md, canonical bytes v1).
3. GET /check/by-hash/{content_hash}
     404            -> not registered. Do not install.
     200 + is_verified true   -> audited SAFE for exactly these bytes. Proceed.
     200 + is_verified false  -> render verdict + trust_score + evidence links. Do not install
                                 automatically; DANGEROUS means stop.
4. To verify independently: follow evidence.audit_tx_url, and/or call
   lookup_by_hash(content_hash) on evidence.registry_contract_id yourself.
5. To read the findings: GET evidence.report_uri, then check
   sha256(bytes) == evidence.evidence_hash from step 3.
```

Step 5's hash check is not optional decoration. `report_uri` points at mutable off-chain
storage; only `evidence_hash` is on the ledger.

---

## 6. Operational notes

- **Caching.** Version records are immutable except through a re-audit, which emits
  `verdict_flipped`. Cache `by-hash` and per-version responses for up to 60 s; invalidate
  immediately on a `verdict_flipped` event. Never cache a `404` for more than a few seconds — a
  skill can be registered at any moment.
- **Fan-out cap.** `GET /skills/{skill_id}` needs one `get_version` per version; cap it at 50
  versions per response and paginate beyond that.
- **Rate limiting.** 100 req/min per IP by default (configurable).
- **CORS.** Open — everything served is public ledger data.
- **Config.** `REGISTRY_CONTRACT_ID` (or `REGISTRY_CA`, the name the deploy scripts write),
  `STELLAR_RPC_URL`, `STELLAR_NETWORK_PASSPHRASE`. Full list with defaults in
  `api/.env.example`. Starting without a contract id logs an error and every read returns
  `503 NOT_CONFIGURED` — it never falls back to mock data.
- **Reads need no keys.** Every read is a `simulateTransaction` from a throwaway source
  account that does not exist on the ledger, so the API holds no secrets.
- **The index is a cache, never a source of truth.** Verdicts are always read from the
  chain per request; the index only supplies the transaction links and `/feed`. Deleting
  the database changes no verdict — it only makes `registration_tx` / `audit_tx` null.
  Rebuild procedure: stop the API, delete `STERISH_DB_PATH`, start it again (or call
  `indexer.rebuild()`); the next poll refills from chain. Covered by
  `api/tests/test_cache_is_not_source_of_truth.py` and the live
  `test_rebuild_from_chain_is_consistent`.

## 7. Change process

Same gate as `docs/specs/interfaces.md` §7. Any change here that is driven by a contract change
must cite the affected invariant (R1–R10 / E1–E8) in the ticket.
