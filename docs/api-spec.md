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

### Implementation status (be honest about this)

Nothing below is implemented yet. `api/src/sterish_api/` currently serves **mock data**
(`client.py::_mock_skills`, still shaped around the removed `latest_verdict`), and
`routes/check.py` additionally has a broken import (`from .models import ... SkillListItem` —
that module lives one level up and defines no `SkillListItem`) plus field names that do not
match `models.py::CheckResponse`. **This file is the target for STE-12**, not a description of
running code. Marked `PLANNED` where it goes beyond the registry contract that exists today.

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

### 3.6 `GET /reports/{skill_id}/{version}` — **PLANNED**

Serves the full verdict JSON (`specs/verdict-json.md`). Bytes MUST hash to the `evidence_hash`
published on-chain for that version; clients are expected to check. Depends on the pipeline
emitting a conforming document (see `verdict-json.md` §7, gaps P1–P8).

### 3.7 `POST /use/{skill_id}/{version}` — **PLANNED (STE-18, x402)**

The paid path: returns `402 Payment Required` with an x402 challenge when the caller holds no
license, and the skill payload plus a freshly minted license token once a USDC micropayment
settles. Depends on the license token contract, which is **not frozen** — see
`specs/interfaces.md` §5.

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
- **Config.** `REGISTRY_CONTRACT_ID`, `STELLAR_RPC_URL`, `STELLAR_NETWORK_PASSPHRASE`. Starting
  without `REGISTRY_CONTRACT_ID` must fail loudly, not silently fall back to mock data (which
  is what `client.py` does today).

## 7. Change process

Same gate as `docs/specs/interfaces.md` §7. Any change here that is driven by a contract change
must cite the affected invariant (R1–R10 / E1–E8) in the ticket.
