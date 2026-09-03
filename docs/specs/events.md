# Sterish — Frozen Event Layouts (v1)

> **STATUS: FROZEN.** These layouts are the handoff contract to the off-chain indexer
> (STE-13), the API (STE-12) and the dashboard (STE-14). Changing a topic or a data key
> silently breaks every consumer, so treat this file as wire format, not documentation.
>
> Companion: `docs/specs/interfaces.md` (functions, errors, invariants).

| | |
|---|---|
| Spec version | `1.0.0` |
| Derived from | `stellar contract info interface --output json` over the built WASM |
| Toolchain | `soroban-sdk 27.0.6`, `stellar-cli 27.0.0`, target `wasm32v1-none` |

## 0. How to regenerate

```bash
cd contracts
cargo build --target wasm32v1-none --release
stellar contract info interface --wasm target/wasm32v1-none/release/sterish_registry.wasm --output json \
  | python3 -c "import json,sys; [print(json.dumps(e['event_v0'],indent=1)) for e in json.load(sys.stdin) if 'event_v0' in e]"
stellar contract info interface --wasm target/wasm32v1-none/release/sterish_escrow.wasm --output json \
  | python3 -c "import json,sys; [print(json.dumps(e['event_v0'],indent=1)) for e in json.load(sys.stdin) if 'event_v0' in e]"
```

Each `event_v0` entry carries `prefix_topics`, a `params` list where every param has a
`location` of either `topic_list` or `data`, and a `data_format`. **Every Sterish event has
`data_format: "map"`** — this was read off the compiled spec, not assumed.

---

## 1. Encoding rules (apply to every event below)

1. **Topics.** `topics[0]` is always `ScSymbol("<event_name>")` — the snake_case prefix topic.
   Then, in declaration order, every field marked `#[topic]`, encoded as its own SCVal.
   `String` fields become `ScString`, `u32` fields become `ScU32`.
2. **Data.** Always a single `ScMap`. Keys are `ScSymbol` field names; values are the fields
   not marked `#[topic]`. This is `data_format: "map"`, so a consumer must look fields up **by
   key** and must never index positionally — adding a field later would silently shift a
   positional reader.
3. **Map key order.** XDR requires `ScMap` keys to be sorted. Soroban's symbol ordering uses
   the 6-bit `SymbolSmall` charset, where `_` sorts after `0-9A-Z` and before `a-z`. Every
   field name in Sterish is lowercase + underscore, so the order is plain lexicographic. The
   key order is listed explicitly per event below — a consumer should still read by key.
4. **`AuditVerdict` / `AuditStatus` values** encode as `ScVec[ScSymbol("<Variant>")]` — the
   variant *name* is on the wire, not an integer. See `interfaces.md` §2.5.
5. **`BytesN<32>`** encodes as `ScBytes` of exactly 32 bytes. Off-chain it is rendered as
   64 lowercase hex characters (the same form as `content_hash` in the verdict JSON).
6. **Ordering within a transaction is significant** and is part of this freeze — see §4.

---

## 2. Registry events

### 2.1 `skill_registered`

Emitted **once per `skill_id`**, the first time it is ever seen, from `register_skill`.

| | |
|---|---|
| Rust type | `SkillRegistered` |
| Emitted by | `register_skill` (only when the skill header did not exist) |
| Topic filter (base64 XDR) | `AAAADwAAABBza2lsbF9yZWdpc3RlcmVk` |

**Topics**

| # | Value | SCVal type |
|---|---|---|
| 0 | `"skill_registered"` | `ScSymbol` |
| 1 | `skill_id` | `ScString` |

**Data** — `ScMap`, keys in this order:

| Key | SCVal type | Meaning |
|---|---|---|
| `owner` | `ScAddress` | The address that registered the skill and now owns it permanently (invariant R1). |

### 2.2 `version_registered`

Emitted for **every** registered version, including the first one.

| | |
|---|---|
| Rust type | `VersionRegistered` |
| Emitted by | `register_skill` (always, after `skill_registered` if that one fired) |
| Topic filter (base64 XDR) | `AAAADwAAABJ2ZXJzaW9uX3JlZ2lzdGVyZWQAAA==` |

**Topics**

| # | Value | SCVal type |
|---|---|---|
| 0 | `"version_registered"` | `ScSymbol` |
| 1 | `skill_id` | `ScString` |
| 2 | `version` | `ScString` |

**Data** — `ScMap`, keys in this order:

| Key | SCVal type | Meaning |
|---|---|---|
| `content_hash` | `ScBytes[32]` | Canonical content hash v1 of the skill bytes (`docs/specs/content-hash.md`). |
| `owner` | `ScAddress` | Version owner; equals the skill owner by R1. |

The version this event announces is **always `Unaudited`** at this point. An indexer must not
treat `version_registered` as any kind of endorsement.

### 2.3 `version_recorded`

The audit handoff event. **This is the one the indexer, the API and the escrow operator care
about. Its shape is explicitly declared "do not change" in `contracts/registry/src/data.rs`.**

| | |
|---|---|
| Rust type | `VersionRecorded` |
| Emitted by | `submit_verdict` (always, and always last) |
| Topic filter (base64 XDR) | `AAAADwAAABB2ZXJzaW9uX3JlY29yZGVk` |

**Topics**

| # | Value | SCVal type |
|---|---|---|
| 0 | `"version_recorded"` | `ScSymbol` |
| 1 | `skill_id` | `ScString` |
| 2 | `version` | `ScString` |

**Data** — `ScMap`, keys in this order:

| Key | SCVal type | Meaning |
|---|---|---|
| `auditor` | `ScAddress` | The auditor address held in instance storage at submission time. |
| `content_hash` | `ScBytes[32]` | Copied from the `VersionRecord`; it is **not** a parameter of `submit_verdict`, so it cannot disagree with what was registered. |
| `trust_score` | `ScU32` | `0..=100`; values above 100 are rejected before emission (`InvalidTrustScore`). |
| `verdict` | `ScVec[ScSymbol]` | One of `Safe` / `Dangerous` / `Warning`. **Never `Unaudited`** — `submit_verdict` rejects it with `InvalidVerdict`(9), so no `version_recorded` with `Unaudited` can exist. |

Consumer notes:

- `evidence_hash` is **not** in this event. It is stored on the `VersionRecord` and must be
  read with `get_version(skill_id, version)`. Deliberate: the event stays small, and the
  evidence anchor is only needed by the path that actually fetches the report.
- The VERIFIED-mint gate is `verdict == Safe`, and only for **this** `version` topic. Never
  key the mint off `skill_id` alone.

### 2.4 `verdict_flipped`

Emitted **only** when a version that already had a non-`Unaudited` verdict receives a
*different* one. Re-submitting the same verdict emits nothing extra.

| | |
|---|---|
| Rust type | `VerdictFlipped` |
| Emitted by | `submit_verdict`, **before** `version_recorded` |
| Topic filter (base64 XDR) | `AAAADwAAAA92ZXJkaWN0X2ZsaXBwZWQA` |

**Topics**

| # | Value | SCVal type |
|---|---|---|
| 0 | `"verdict_flipped"` | `ScSymbol` |
| 1 | `skill_id` | `ScString` |
| 2 | `version` | `ScString` |

**Data** — `ScMap`, keys in this order:

| Key | SCVal type | Meaning |
|---|---|---|
| `new_verdict` | `ScVec[ScSymbol]` | The verdict being written now. |
| `old_verdict` | `ScVec[ScSymbol]` | The verdict being replaced; never `Unaudited` (that case emits nothing). |

> The field names are `old_verdict` / `new_verdict` rather than `old` / `new` because `new` is
> a Rust keyword. That naming is now wire format and cannot be "cleaned up".

A flip to anything other than `Safe` is the revocation signal: any VERIFIED badge minted for
that `(skill_id, version)` must be treated as stale by consumers.

---

## 3. Escrow events

### 3.1 `request_created`

| | |
|---|---|
| Rust type | `RequestCreated` |
| Emitted by | `create_audit_request`, after the fee transfer succeeds |
| Topic filter (base64 XDR) | `AAAADwAAAA9yZXF1ZXN0X2NyZWF0ZWQA` |

**Topics**

| # | Value | SCVal type |
|---|---|---|
| 0 | `"request_created"` | `ScSymbol` |
| 1 | `request_id` | `ScU32` |

**Data** — `ScMap`, keys in this order:

| Key | SCVal type | Meaning |
|---|---|---|
| `fee` | `ScI128` | USDC amount pulled from the requestor, in stroops (7 decimals). Note the key is `fee`, while the struct field on `AuditRequest` is `fee_amount`. |
| `requestor` | `ScAddress` | Who opened and funded the job. |
| `skill_id` | `ScString` | Registry skill under audit. |

> ⚠️ **`version` and `bond_amount` are NOT in this event**, even though both are stored on the
> `AuditRequest`. A consumer that needs them must call `get_request(request_id)`. This is a
> known sharp edge of the frozen layout: an indexer cannot tie a job to an exact
> `(skill_id, version)` from the event stream alone.

### 3.2 `bond_posted`

| | |
|---|---|
| Rust type | `BondPosted` |
| Emitted by | `post_bond`, after the bond transfer succeeds |
| Topic filter (base64 XDR) | `AAAADwAAAAtib25kX3Bvc3RlZAA=` |

**Topics**

| # | Value | SCVal type |
|---|---|---|
| 0 | `"bond_posted"` | `ScSymbol` |
| 1 | `request_id` | `ScU32` |

**Data** — `ScMap`, keys in this order:

| Key | SCVal type | Meaning |
|---|---|---|
| `auditor` | `ScAddress` | Auditor who took the job; guaranteed `!= requestor` (E4). |
| `bond` | `ScI128` | Always exactly `request.bond_amount` (E1). |

### 3.3 `settled`

| | |
|---|---|
| Rust type | `Settled` |
| Emitted by | `settle`, after the payout transfer |
| Topic filter (base64 XDR) | `AAAADwAAAAdzZXR0bGVkAA==` |

**Topics**

| # | Value | SCVal type |
|---|---|---|
| 0 | `"settled"` | `ScSymbol` |
| 1 | `request_id` | `ScU32` |

**Data** — `ScMap`:

| Key | SCVal type | Meaning |
|---|---|---|
| `payout` | `ScI128` | `fee_amount + bond_amount`, paid to the auditor. The recipient address is not in the event — read `get_request(request_id).auditor`. |

### 3.4 `slashed`

| | |
|---|---|
| Rust type | `Slashed` |
| Emitted by | `slash` and `claim_forfeited` (the latter with `reporter == admin`) |
| Topic filter (base64 XDR) | `AAAADwAAAAdzbGFzaGVkAA==` |

**Topics**

| # | Value | SCVal type |
|---|---|---|
| 0 | `"slashed"` | `ScSymbol` |
| 1 | `request_id` | `ScU32` |

**Data** — `ScMap`, keys in this order:

| Key | SCVal type | Meaning |
|---|---|---|
| `bond` | `ScI128` | Bond forfeited to `reporter`. |
| `reporter` | `ScAddress` | Who receives the bond. Equals the admin when the call was `claim_forfeited`. |

> `slash` and `claim_forfeited` are **indistinguishable in the event stream** — both emit
> `slashed`. To tell them apart, compare `reporter` against `get_admin()`. This is accepted,
> because `claim_forfeited(id)` is defined as exactly equivalent to `slash(id, admin)`.
>
> The fee refund to the requestor is *not* announced by a Sterish event; it appears only as a
> SAC `transfer` event from the USDC contract in the same transaction.

---

## 4. Emission order (frozen)

Order within a single transaction is part of the contract, because a consumer that folds
events in stream order must land on the right final state.

| Call | Events, in order |
|---|---|
| `register_skill` — first version of a new skill | `skill_registered`, then `version_registered` |
| `register_skill` — subsequent version | `version_registered` only |
| `submit_verdict` — first verdict for the version | `version_recorded` only |
| `submit_verdict` — re-audit, verdict changed | `verdict_flipped`, then `version_recorded` |
| `submit_verdict` — re-audit, same verdict | `version_recorded` only |
| `create_audit_request` | USDC SAC `transfer`, then `request_created` |
| `post_bond` | USDC SAC `transfer`, then `bond_posted` |
| `settle` | USDC SAC `transfer`, then `settled` |
| `slash` / `claim_forfeited` | two USDC SAC `transfer`s (bond→reporter, then fee→requestor), then `slashed` |

A failed call emits nothing: every event is published after the state write and after any
token transfer, and any error unwinds the whole transaction.

---

## 5. Consuming the stream (indexer notes, STE-13)

Minimal `getEvents` filter for the trust-relevant stream:

```jsonc
{
  "jsonrpc": "2.0", "id": 1, "method": "getEvents",
  "params": {
    "startLedger": <deploy ledger>,
    "filters": [{
      "type": "contract",
      "contractIds": ["<REGISTRY_CONTRACT_ID>"],
      "topics": [
        ["AAAADwAAABB2ZXJzaW9uX3JlY29yZGVk", "*", "*"],   // version_recorded
        ["AAAADwAAAA92ZXJkaWN0X2ZsaXBwZWQA", "*", "*"]    // verdict_flipped
      ]
    }],
    "pagination": { "limit": 100 }
  }
}
```

Rules for consumers:

1. **Read data by map key, never by position.** `data_format` is `map` for a reason.
2. **Key everything on `(skill_id, version)`, never on `skill_id` alone.** The whole point of
   invariant R4 is that a verdict belongs to one version.
3. **`content_hash` from `version_recorded` is authoritative** for the "what exactly was
   audited" question — it is copied from the stored record, not passed in by the auditor.
4. **Treat `verdict_flipped` as a revocation trigger**, not just a log line.
5. Stellar RPC retains only a limited window of ledgers (~7 days on testnet). An indexer that
   falls behind that window must backfill from contract state
   (`query_all_skills` + `get_version`), not from events.
6. Escrow events alone are not enough to reconstruct a job — `version` and `bond_amount` are
   only reachable via `get_request(request_id)` (see §3.1).

---

## 6. Change process

Same gate as `docs/specs/interfaces.md` §7. In addition, any change to a topic tuple or to a
data map key must state explicitly how the indexer backfills history written under the old
layout, because past ledgers cannot be rewritten.
