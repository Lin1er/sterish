# Sterish — Frozen Contract Interfaces (v1)

> **STATUS: FROZEN** for `sterish-registry` and `sterish-escrow`.
> Everything in the "Generated ABI" blocks below is machine-generated from the WASM
> that is actually built from `main`. It is **not** hand-written, and it is **not** a
> design document. Where this file and `docs/SYSTEM_DESIGN.md` disagree, **this file
> wins** — the divergences are listed in [§6](#6-divergences-from-the-design-doc).

| | |
|---|---|
| Spec version | `1.0.0` |
| Frozen at | STE-10, branch `feat/6-freeze-interface-hash-spec` |
| Source contracts | `contracts/registry` (STE-5, merged), `contracts/escrow` (STE-9, merged) |
| Toolchain | `soroban-sdk 27.0.6`, `stellar-cli 27.0.0`, `rustc 1.93.0`, target `wasm32v1-none` |

## 0. How to regenerate this file

```bash
cd contracts
cargo build --target wasm32v1-none --release
stellar contract info interface --wasm target/wasm32v1-none/release/sterish_registry.wasm
stellar contract info interface --wasm target/wasm32v1-none/release/sterish_escrow.wasm
```

Machine-readable form (used to derive the event tables in `events.md`):

```bash
stellar contract info interface --wasm target/wasm32v1-none/release/sterish_registry.wasm --output json
```

Any diff between the output of those commands and the "Generated ABI" blocks below is a
**breaking change** and must go through the change process in `docs/specs/README.md`.

## 1. What "frozen" means here

Frozen = the following are part of the public ABI and may not change without a version bump:

1. **Function names and parameter order.** Soroban invokes by name; renaming or reordering
   breaks every deployed client, indexer and CLI script.
2. **Error discriminants.** `RegistryError`/`EscrowError` numbers travel on-chain inside
   `ScError`. Renumbering silently re-labels historical failed transactions.
3. **`#[contracttype]` struct field names**, because unit-struct types encode as an `ScMap`
   keyed by the field-name symbol — a rename is a wire-format change, not a cosmetic one.
4. **Enum variant order** for `AuditVerdict` and `AuditStatus`. Unit variants encode as
   `ScVec[ScSymbol("<VariantName>")]`, so the *name* is on the wire; the order is frozen
   anyway so that any numeric mapping used off-chain stays stable.
5. **Event topics and data layout** — see `docs/specs/events.md`.

Not frozen: doc comments, internal storage helpers (`bump_*`), TTL constants
(`BUMP_THRESHOLD` / `BUMP_TO` are tuning parameters, not ABI).

---

## 2. Registry — `sterish_registry`

### 2.1 Generated ABI

<!-- BEGIN GENERATED: stellar contract info interface --wasm target/wasm32v1-none/release/sterish_registry.wasm -->
```rust
#[soroban_sdk::contractargs(name = "Args")]
#[soroban_sdk::contractclient(name = "Client")]
pub trait Contract {
    fn get_admin(env: soroban_sdk::Env) -> Result<soroban_sdk::Address, RegistryError>;
    fn get_latest(
        env: soroban_sdk::Env,
        skill_id: soroban_sdk::String,
    ) -> Result<VersionRecord, RegistryError>;
    fn get_auditor(env: soroban_sdk::Env) -> Result<soroban_sdk::Address, RegistryError>;
    fn get_version(
        env: soroban_sdk::Env,
        skill_id: soroban_sdk::String,
        version: soroban_sdk::String,
    ) -> Result<VersionRecord, RegistryError>;
    fn is_verified(
        env: soroban_sdk::Env,
        skill_id: soroban_sdk::String,
        version: soroban_sdk::String,
    ) -> bool;
    fn query_skill(
        env: soroban_sdk::Env,
        skill_id: soroban_sdk::String,
    ) -> Result<SkillEntry, RegistryError>;
    fn set_auditor(
        env: soroban_sdk::Env,
        auditor: soroban_sdk::Address,
    ) -> Result<(), RegistryError>;
    fn __constructor(
        env: soroban_sdk::Env,
        admin: soroban_sdk::Address,
        auditor: soroban_sdk::Address,
    );
    fn lookup_by_hash(
        env: soroban_sdk::Env,
        content_hash: soroban_sdk::BytesN<32>,
    ) -> Option<VersionRecord>;
    fn register_skill(
        env: soroban_sdk::Env,
        owner: soroban_sdk::Address,
        skill_id: soroban_sdk::String,
        version: soroban_sdk::String,
        content_hash: soroban_sdk::BytesN<32>,
    ) -> Result<(), RegistryError>;
    fn submit_verdict(
        env: soroban_sdk::Env,
        skill_id: soroban_sdk::String,
        version: soroban_sdk::String,
        verdict: AuditVerdict,
        score: u32,
        evidence_hash: soroban_sdk::BytesN<32>,
    ) -> Result<(), RegistryError>;
    fn get_skill_count(env: soroban_sdk::Env) -> u32;
    fn query_all_skills(
        env: soroban_sdk::Env,
        start: u32,
        limit: u32,
    ) -> soroban_sdk::Vec<SkillEntry>;
    fn get_trust_score_config(env: soroban_sdk::Env) -> TrustScoreConfig;
    fn update_trust_score_config(
        env: soroban_sdk::Env,
        config: TrustScoreConfig,
    ) -> Result<(), RegistryError>;
}
#[soroban_sdk::contracttype(export = false)]
#[derive(Debug, Clone, Eq, PartialEq, Ord, PartialOrd)]
pub struct SkillEntry {
    pub latest_audited_version: Option<soroban_sdk::String>,
    pub latest_version: soroban_sdk::String,
    pub owner: soroban_sdk::Address,
    pub registered_at: u64,
    pub skill_id: soroban_sdk::String,
    pub versions: soroban_sdk::Vec<soroban_sdk::String>,
}
#[soroban_sdk::contracttype(export = false)]
#[derive(Debug, Clone, Eq, PartialEq, Ord, PartialOrd)]
pub struct VersionRecord {
    pub audited_at: u64,
    pub auditor: Option<soroban_sdk::Address>,
    pub content_hash: soroban_sdk::BytesN<32>,
    pub evidence_hash: soroban_sdk::BytesN<32>,
    pub owner: soroban_sdk::Address,
    pub registered_at: u64,
    pub skill_id: soroban_sdk::String,
    pub trust_score: u32,
    pub verdict: AuditVerdict,
    pub version: soroban_sdk::String,
}
#[soroban_sdk::contracttype(export = false)]
#[derive(Debug, Clone, Eq, PartialEq, Ord, PartialOrd)]
pub struct TrustScoreConfig {
    pub desc_weight: u32,
    pub reputation_weight: u32,
    pub sandbox_weight: u32,
}
#[soroban_sdk::contracttype(export = false)]
#[derive(Debug, Clone, Eq, PartialEq, Ord, PartialOrd)]
pub enum DataKey {
    Admin,
    Auditor,
    TrustConfig,
    SkillCount,
    Skill(soroban_sdk::String),
    Version(soroban_sdk::String, soroban_sdk::String),
    HashIndex(soroban_sdk::BytesN<32>),
    SkillIndex(u32),
}
#[soroban_sdk::contracttype(export = false)]
#[derive(Debug, Clone, Eq, PartialEq, Ord, PartialOrd)]
pub enum AuditVerdict {
    Unaudited,
    Safe,
    Dangerous,
    Warning,
}
#[soroban_sdk::contracterror(export = false)]
#[derive(Debug, Copy, Clone, Eq, PartialEq, Ord, PartialOrd)]
pub enum RegistryError {
    NotInitialized = 1,
    NotAuthorized = 2,
    SkillNotFound = 3,
    VersionNotFound = 4,
    VersionAlreadyExists = 5,
    HashAlreadyRegistered = 6,
    InvalidInput = 7,
    InvalidTrustScore = 8,
    InvalidVerdict = 9,
}
```
<!-- END GENERATED -->

Event types are omitted from this block on purpose — they are in `docs/specs/events.md`.

> **Note on field order.** The generated block prints struct fields alphabetically because
> that is the `ScMap` key order on the wire, not the declaration order in `data.rs`. The
> wire order is the frozen one.

### 2.2 Function reference

Auth column: `require_auth()` on which address. "Reads" functions are safe to call through
`simulateTransaction` with no signature at all.

| Function | Auth | Mutates | Returns | Errors | Events |
|---|---|---|---|---|---|
| `__constructor(admin, auditor)` | none (runs atomically at deploy) | `Admin`, `Auditor`, `TrustConfig`(default), `SkillCount=0` | `()` | — | none |
| `register_skill(owner, skill_id, version, content_hash)` | `owner` | `Skill`, `Version`, `HashIndex`, `SkillIndex`, `SkillCount` | `()` | `InvalidInput`(7), `NotAuthorized`(2), `VersionAlreadyExists`(5), `HashAlreadyRegistered`(6) | `skill_registered` (first version only) **then** `version_registered` (always) |
| `submit_verdict(skill_id, version, verdict, score, evidence_hash)` | `auditor` (from instance storage) | `Version`, `Skill.latest_audited_version` | `()` | `NotInitialized`(1), `InvalidTrustScore`(8), `InvalidVerdict`(9), `SkillNotFound`(3), `VersionNotFound`(4) | `verdict_flipped` (only on a real flip) **then** `version_recorded` (always) |
| `lookup_by_hash(content_hash)` | none | — | `Option<VersionRecord>` | never errors — a miss is `None` | none |
| `get_version(skill_id, version)` | none | — | `VersionRecord` | `SkillNotFound`(3), `VersionNotFound`(4) | none |
| `get_latest(skill_id)` | none | — | `VersionRecord` of the last **registered** version | `SkillNotFound`(3), `VersionNotFound`(4) | none |
| `is_verified(skill_id, version)` | none | — | `bool` | never errors — unknown is `false` | none |
| `query_skill(skill_id)` | none | — | `SkillEntry` | `SkillNotFound`(3) | none |
| `query_all_skills(start, limit)` | none | — | `Vec<SkillEntry>` (may be shorter than `limit`) | never errors | none |
| `set_auditor(auditor)` | `admin` | `Auditor` | `()` | `NotInitialized`(1) | none |
| `update_trust_score_config(config)` | `admin` | `TrustConfig` | `()` | `NotInitialized`(1) | none |
| `get_trust_score_config()` | none | — | `TrustScoreConfig` (defaults 40/40/20 if unset) | never errors | none |
| `get_auditor()` | none | — | `Address` | `NotInitialized`(1) | none |
| `get_admin()` | none | — | `Address` | `NotInitialized`(1) | none |
| `get_skill_count()` | none | — | `u32` (0 if unset) | never errors | none |

### 2.3 Frozen invariants (enforced by code, covered by tests)

| # | Invariant | Enforced by |
|---|---|---|
| R1 | A `skill_id` has exactly one owner; only that owner may add versions. | `register_skill` → `NotAuthorized` |
| R2 | A `(skill_id, version)` pair is write-once and immutable. | `register_skill` → `VersionAlreadyExists` |
| R3 | A `content_hash` maps to exactly one `(skill_id, version)`; hash squatting is impossible and `lookup_by_hash` is never ambiguous. | `register_skill` → `HashAlreadyRegistered` |
| R4 | The verdict lives on the **version record**, never on the skill header. Auditing v1 says nothing about v2. | `VersionRecord.verdict`; `SkillEntry` has **no** `latest_verdict` field |
| R5 | `Unaudited` can never be *submitted*; it is only the initial state written by `register_skill`. | `submit_verdict` → `InvalidVerdict`(9) |
| R6 | `score > 100` is rejected outright — never silently clamped. | `submit_verdict` → `InvalidTrustScore`(8) |
| R7 | `is_verified` is `true` only for `verdict == Safe` on **that exact version**. This is the sole gate for minting VERIFIED. | `is_verified` |
| R8 | A `lookup_by_hash` miss returns `None`, never a panic and never a neighbouring version's record. | `lookup_by_hash` |
| R9 | Unbounded state (`Skill`, `Version`, `HashIndex`, `SkillIndex`) is **persistent** and TTL-bumped on every write; only bounded state (`Admin`, `Auditor`, `TrustConfig`, `SkillCount`) is in instance storage. | `bump_persistent` / `bump_instance`, `DataKey` layout |
| R10 | Deploy and initialization are atomic (`__constructor`), so there is no window in which a third party can claim admin. | `__constructor` |

### 2.4 Storage layout (frozen keys)

| Key | Durability | Value |
|---|---|---|
| `Admin` | instance | `Address` |
| `Auditor` | instance | `Address` |
| `TrustConfig` | instance | `TrustScoreConfig` |
| `SkillCount` | instance | `u32` |
| `Skill(skill_id)` | persistent | `SkillEntry` |
| `Version(skill_id, version)` | persistent | `VersionRecord` |
| `HashIndex(content_hash)` | persistent | `(String, String)` = `(skill_id, version)` |
| `SkillIndex(u32)` | persistent | `String` = `skill_id` |

TTL policy (tuning, not ABI): `BUMP_THRESHOLD = 30 × 17_280` ledgers, `BUMP_TO = 120 × 17_280` ledgers.

### 2.5 `AuditVerdict` on the wire

`AuditVerdict` is a `#[contracttype]` enum with unit variants only, so a value encodes as
`ScVec[ScSymbol("<Variant>")]` — **the variant name is on the wire, not an integer**.

| Variant | Index | XDR | JSON verdict string (see `verdict-json.md`) |
|---|---|---|---|
| `Unaudited` | 0 | `ScVec[ScSymbol("Unaudited")]` | `"UNAUDITED"` — never submitted |
| `Safe` | 1 | `ScVec[ScSymbol("Safe")]` | `"SAFE"` |
| `Dangerous` | 2 | `ScVec[ScSymbol("Dangerous")]` | `"DANGEROUS"` |
| `Warning` | 3 | `ScVec[ScSymbol("Warning")]` | `"WARNING"` |

CLI form: `--verdict '{"vec":[{"symbol":"Safe"}]}'`, or with the typed CLI simply `--verdict Safe`.

> ⚠️ **Known caller bug (not this ticket's file).** `pipeline/src/sterish_pipeline/onchain.py`
> still encodes the verdict as `scval.to_uint32(1|2|3)` and calls `submit_verdict` with only
> **four** arguments (no `version`). Both are wrong against this frozen ABI. Tracked in
> [§6](#6-divergences-from-the-design-doc), to be fixed by the ticket that owns the pipeline
> submitter (STE-13).

---

## 3. Escrow — `sterish_escrow`

### 3.1 Generated ABI

<!-- BEGIN GENERATED: stellar contract info interface --wasm target/wasm32v1-none/release/sterish_escrow.wasm -->
```rust
#[soroban_sdk::contractargs(name = "Args")]
#[soroban_sdk::contractclient(name = "Client")]
pub trait Contract {
    fn slash(
        env: soroban_sdk::Env,
        request_id: u32,
        reporter: soroban_sdk::Address,
    ) -> Result<(), EscrowError>;
    fn settle(env: soroban_sdk::Env, request_id: u32) -> Result<(), EscrowError>;
    fn get_admin(env: soroban_sdk::Env) -> Result<soroban_sdk::Address, EscrowError>;
    fn post_bond(
        env: soroban_sdk::Env,
        auditor: soroban_sdk::Address,
        request_id: u32,
    ) -> Result<(), EscrowError>;
    fn get_request(
        env: soroban_sdk::Env,
        request_id: u32,
    ) -> Result<AuditRequest, EscrowError>;
    fn __constructor(
        env: soroban_sdk::Env,
        usdc_token: soroban_sdk::Address,
        admin: soroban_sdk::Address,
    );
    fn get_usdc_token(
        env: soroban_sdk::Env,
    ) -> Result<soroban_sdk::Address, EscrowError>;
    fn claim_forfeited(
        env: soroban_sdk::Env,
        request_id: u32,
    ) -> Result<(), EscrowError>;
    fn get_request_count(env: soroban_sdk::Env) -> u32;
    fn create_audit_request(
        env: soroban_sdk::Env,
        requestor: soroban_sdk::Address,
        skill_id: soroban_sdk::String,
        version: soroban_sdk::String,
        fee_amount: i128,
        bond_amount: i128,
    ) -> Result<u32, EscrowError>;
}
#[soroban_sdk::contracttype(export = false)]
#[derive(Debug, Clone, Eq, PartialEq, Ord, PartialOrd)]
pub struct AuditRequest {
    pub auditor: Option<soroban_sdk::Address>,
    pub bond_amount: i128,
    pub created_at: u64,
    pub fee_amount: i128,
    pub requestor: soroban_sdk::Address,
    pub resolved_at: u64,
    pub skill_id: soroban_sdk::String,
    pub status: AuditStatus,
    pub version: soroban_sdk::String,
}
#[soroban_sdk::contracttype(export = false)]
#[derive(Debug, Clone, Eq, PartialEq, Ord, PartialOrd)]
pub enum StorageKey {
    UsdcToken,
    Admin,
    NextRequestId,
    Request(u32),
}
#[soroban_sdk::contracttype(export = false)]
#[derive(Debug, Clone, Eq, PartialEq, Ord, PartialOrd)]
pub enum AuditStatus {
    Open,
    Bonded,
    Settled,
    Slashed,
}
#[soroban_sdk::contracterror(export = false)]
#[derive(Debug, Copy, Clone, Eq, PartialEq, Ord, PartialOrd)]
pub enum EscrowError {
    NotInitialized = 1,
    RequestNotFound = 2,
    NotOpen = 3,
    NotBonded = 4,
    AlreadySettled = 5,
    AlreadySlashed = 6,
    InvalidAmount = 7,
    InvalidInput = 8,
    SelfAudit = 9,
}
```
<!-- END GENERATED -->

### 3.2 Function reference

All money moves are `TokenClient::transfer` against the USDC SAC stored at `UsdcToken`.

| Function | Auth | USDC movement | Returns | Errors | Events |
|---|---|---|---|---|---|
| `__constructor(usdc_token, admin)` | none (atomic at deploy) | — | `()` | — | none |
| `create_audit_request(requestor, skill_id, version, fee_amount, bond_amount)` | `requestor` | `requestor → contract` = `fee_amount` | `u32` `request_id` (starts at 1) | `InvalidInput`(8) on empty id/version, `InvalidAmount`(7) if `fee<=0 \|\| bond<=0`, `NotInitialized`(1); reverts if the token transfer fails | `request_created` |
| `post_bond(auditor, request_id)` | `auditor` | `auditor → contract` = `request.bond_amount` (exactly; no amount parameter exists) | `()` | `RequestNotFound`(2); wrong state → `NotOpen`(3) if already `Bonded`, `AlreadySettled`(5), `AlreadySlashed`(6); `SelfAudit`(9), `NotInitialized`(1) | `bond_posted` |
| `settle(request_id)` | `admin` | `contract → auditor` = `fee + bond` | `()` | `RequestNotFound`(2); wrong state → `NotBonded`(4) if still `Open`, `AlreadySettled`(5), `AlreadySlashed`(6); `InvalidAmount`(7) on `i128` overflow | `settled` |
| `slash(request_id, reporter)` | `admin` | `contract → reporter` = `bond`; `contract → requestor` = `fee` | `()` | same set as `settle` | `slashed` |
| `claim_forfeited(request_id)` | `admin` | identical to `slash(request_id, admin)` | `()` | same set as `slash` | `slashed` (with `reporter == admin`) |
| `get_request(request_id)` | none | — | `AuditRequest` | `RequestNotFound`(2) | none |
| `get_usdc_token()` | none | — | `Address` | `NotInitialized`(1) | none |
| `get_admin()` | none | — | `Address` | `NotInitialized`(1) | none |
| `get_request_count()` | none | — | `u32` = `NextRequestId - 1` | never errors | none |

### 3.3 State machine (frozen)

```
                create_audit_request            post_bond
   (nothing) ─────────────────────────▶ Open ─────────────────▶ Bonded
                fee: requestor→contract       bond: auditor→contract
                                                                  │
                                    settle                        │
                    ┌─────────────────────────────────────────────┤
                    ▼                                             ▼
                 Settled  (terminal)                    slash / claim_forfeited
             fee+bond → auditor                                   │
                                                                  ▼
                                                          Slashed  (terminal)
                                              bond → reporter, fee → requestor
```

Error mapping when a call hits the wrong state (`require_status`): current `Settled` →
`AlreadySettled`(5); current `Slashed` → `AlreadySlashed`(6); current `Open` when `Bonded`
was required → `NotBonded`(4); current `Bonded` when `Open` was required → `NotOpen`(3).

### 3.4 Frozen invariants

| # | Invariant | Enforced by |
|---|---|---|
| E1 | The bond amount is fixed by the **paying party at create time**; `post_bond` transfers exactly `request.bond_amount`. An auditor cannot bond 1 stroop and still collect `fee + bond`. | `post_bond` has no `amount` parameter |
| E2 | `Settled` and `Slashed` are terminal. No money can move for a job after it leaves `Bonded`. | `require_status(..., Bonded)` in `settle` / `slash_to` |
| E3 | `claim_forfeited` performs the terminal transition itself and requires `Bonded`, so a second call fails with `AlreadySlashed` and cannot drain other jobs' escrowed balance. | `slash_to` shared body |
| E4 | The requestor cannot audit their own job. | `post_bond` → `SelfAudit`(9) |
| E5 | `auditor` is `Option<Address>` — `None` means "not bonded", which is distinguishable from "self-audited". | `AuditRequest.auditor` |
| E6 | Amount signs are validated explicitly, because a SAC reads `transfer(from, to, -n)` as a pull in the opposite direction. | `create_audit_request` → `InvalidAmount`(7) |
| E7 | Exactly one counter (`NextRequestId`); the count is derived, so two counters cannot drift. | `get_request_count` |
| E8 | Job entries are persistent and TTL-bumped on every write, so a job cannot be archived out from under escrowed funds. | `bump_request` |

### 3.5 MVP authorization note (frozen, deliberately)

`settle` / `slash` / `claim_forfeited` are **admin-gated**, and nothing on-chain verifies the
verdict. The admin key is the same key that holds the auditor role on the Registry; the source
of truth is the Registry's `version_recorded` event, read **off-chain** by the operator before
calling. A dispute window and an on-chain verdict-gated path are explicitly out of MVP scope
(see `docs/SYSTEM_DESIGN.md` §4.2 and `docs/architecture.md` §2).

---

## 4. Cross-contract linkage

The Escrow does **not** call the Registry. The link is by value only:
`AuditRequest.skill_id` + `AuditRequest.version` name the exact `VersionRecord` being paid for.
An operator settling a job must check that `(skill_id, version)` on the request matches the
`(skill_id, version)` topics of the `version_recorded` event it is settling against.

---

## 5. VERIFIED token + license token — **STATUS: PLANNED — NOT FROZEN**

> 🚧 **These contracts do not exist yet.** There is no code in `contracts/` for them, so
> nothing below is generated from a WASM and nothing below is binding. This section is the
> *intended shape* for STE-11 so that the API and dashboard specs have something to name.
> **Do not implement clients against it.** When STE-11 lands, this section is replaced by a
> generated ABI block and the `PLANNED` marker is removed.

### 5.1 Decisions already fixed by `CLAUDE.md` (these will carry into the frozen version)

- Both tokens are **soulbound**: non-transferable, and the transfer entrypoints are not
  exported at all (not merely reverting).
- Only `AuditVerdict::Safe` may trigger a VERIFIED mint. The mint path must consult
  `SkillRegistry::is_verified(skill_id, version)` and refuse otherwise.
- Base standard: OpenZeppelin Stellar non-fungible, with the transfer/approval surface removed.

### 5.2 Planned interface sketch (illustrative, subject to change)

```rust
// PLANNED — sterish_verified (soulbound badge, one token per audited-Safe version)
pub trait VerifiedToken {
    fn __constructor(env: Env, admin: Address, registry: Address);
    /// Mints to the version owner. MUST call registry.is_verified(skill_id, version)
    /// and fail with NotSafe if it returns false. Idempotent per (skill_id, version).
    fn mint_verified(env: Env, skill_id: String, version: String) -> Result<u32, VerifiedError>;
    fn token_of(env: Env, skill_id: String, version: String) -> Option<u32>;
    fn owner_of(env: Env, token_id: u32) -> Result<Address, VerifiedError>;
    // NO transfer / transfer_from / approve — soulbound.
}

// PLANNED — sterish_license (soulbound per-agent, per-version access token)
pub trait LicenseToken {
    fn __constructor(env: Env, admin: Address, registry: Address, usdc: Address);
    /// Called by the x402 settlement path after a USDC micropayment clears.
    fn mint_license(env: Env, to: Address, skill_id: String, version: String)
        -> Result<u32, LicenseError>;
    fn has_license(env: Env, holder: Address, skill_id: String, version: String) -> bool;
    // NO transfer — soulbound.
}
```

### 5.3 Open questions for STE-11 (need an Axel decision)

1. Does a license bind to `(skill_id, version)` or to `content_hash`? Binding to
   `content_hash` makes "the license goes stale on the next audited version" automatic and
   matches `lookup_by_hash`, but it makes the token id harder to read for a human.
2. Royalties: `SYSTEM_DESIGN.md` §5 mentions OZ Royalties for an author cut on each license.
   Royalties on a **soulbound** token only make sense at mint time, not on resale — confirm
   that a mint-time author cut is what is wanted, or drop the extension.
3. Who may call `mint_license` — only the x402 facilitator settlement address, or the API
   admin key as well?

---

## 6. Divergences from the design doc

Found while freezing. **In every row the merged code is authoritative** and the doc/caller is
the thing that is wrong.

| # | Where | Doc / caller says | Merged code does | Resolution |
|---|---|---|---|---|
| D1 | `SYSTEM_DESIGN.md` §4.1 | one function `record_version(skill_id, content_hash, verdict, trust_score, risk, report_uri) -> version` | two functions: `register_skill(owner, skill_id, version, content_hash)` (owner-authed) and `submit_verdict(skill_id, version, verdict, score, evidence_hash)` (auditor-authed) | Code wins. Registration and auditing are different actors with different auth; merging them would let the auditor role register skills. |
| D2 | `SYSTEM_DESIGN.md` §4.1 `Version(...)` value | includes a `risk` field | `VersionRecord` has **no** `risk` field | Code wins. `risk` stays off-chain in the verdict JSON; on-chain carries `verdict` + `trust_score` only, and `evidence_hash` anchors the rest. |
| D3 | `SYSTEM_DESIGN.md` §4.1 `Version(...)` value | includes `report_uri: String` | `VersionRecord` has **no** `report_uri`; it has `evidence_hash: BytesN<32>` | Code wins. A URI is mutable off-chain and gives false assurance; a hash does not. The API serves `report_uri` from its own index and clients verify it against `evidence_hash`. |
| D4 | `SYSTEM_DESIGN.md` §4.1 | `record_version` "bumps `latest_version`" | `submit_verdict` bumps `latest_audited_version`; `latest_version` is bumped by `register_skill` | Code wins. Two distinct pointers: last **registered** vs last **audited**. Conflating them is the badge-inheritance bug. |
| D5 | `SYSTEM_DESIGN.md` §4.1 | `lookup_by_hash(content_hash) -> (skill_id, v)` | returns `Option<VersionRecord>` — the whole record, one call | Code wins (strictly better: no second round-trip, and a miss is `None`). |
| D6 | `SYSTEM_DESIGN.md` §4.1 events | `version_recorded(..., risk, ...)` | `version_recorded` data map has no `risk` — see `events.md` | Code wins, follows D2. |
| D7 | `docs/api-spec.md` (pre-STE-10) | `GET /check/{skill_id}` returns a single `verdict` for the skill header | verdict is **per version**; `SkillEntry` has no `latest_verdict` | api-spec.md rewritten in this ticket; see §1 of the new `docs/api-spec.md`. |
| D8 | `pipeline/src/sterish_pipeline/onchain.py` | calls `submit_verdict(skill_id, u32_verdict, score, evidence)` — 4 args, verdict as `u32` | signature is 5 args `(skill_id, version, verdict, score, evidence_hash)` and the verdict is `ScVec[ScSymbol]`, not `u32` | **Caller is broken against the frozen ABI.** Not fixed here (not this ticket's file). Must be fixed by STE-13 before any real submission. |
| D9 | `api/src/sterish_api/client.py` mock | mock records carry `latest_verdict` and `evidence_url` | neither exists on-chain | The mock must be replaced by real RPC reads in STE-12; the new `api-spec.md` is the target shape. |
| D10 | `api/src/sterish_api/routes/check.py` | imports `from .models import ... SkillListItem` and constructs `CheckResponse(evidence=..., audit_timestamp=str)` | `api/src/sterish_api/models.py` (one level up) defines no `SkillListItem`, and `CheckResponse` wants `evidence_hash` + `int` timestamp | Pre-existing import/field bug in the scaffolded API — flagged for STE-12, not fixed here. |

---

## 7. Change process

This file is frozen. To change anything in §2 or §3:

1. Open a ticket that states which of R1–R10 / E1–E8 it affects.
2. Bump the spec version at the top of this file and record it in `docs/specs/README.md`'s
   changelog.
3. Rebuild the WASM and paste a fresh generated block — never hand-edit inside the
   `BEGIN GENERATED` markers.
4. Re-check `docs/specs/events.md` and `docs/api-spec.md`, which are derived from this file.

§5 (tokens) is *not* frozen and may be edited freely until STE-11 lands.
