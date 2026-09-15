use soroban_sdk::{contracterror, contractevent, contracttype, Address, BytesN, String, Vec};

/// Approximate number of ledgers closed in a day (5s close time).
pub const DAY_IN_LEDGERS: u32 = 17_280;
/// Only extend an entry's TTL when it drops below this many ledgers.
pub const BUMP_THRESHOLD: u32 = 30 * DAY_IN_LEDGERS;
/// TTL floor (in ledgers) every touched entry is bumped to.
pub const BUMP_TO: u32 = 120 * DAY_IN_LEDGERS;

/// Audit verdict for one specific skill version.
///
/// FINAL decision (see CLAUDE.md): only `Safe` is allowed to mint a VERIFIED badge.
/// A poisoned skill MUST end up as `Dangerous`.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AuditVerdict {
    Unaudited,
    Safe,
    Dangerous,
    Warning,
}

/// The audit record of a single (skill_id, version) pair.
///
/// This is the ONLY source of truth for verdict / trust score / auditor / evidence.
/// `SkillEntry` deliberately does NOT carry a `latest_verdict` anymore: that was the
/// scaffold bug where a rug-pulled v2 could inherit the badge audited for v1.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VersionRecord {
    pub skill_id: String,
    pub version: String,
    pub content_hash: BytesN<32>,
    /// Address that registered this version.
    pub owner: Address,
    pub registered_at: u64,
    /// `Unaudited` until an auditor submits a verdict for THIS version.
    pub verdict: AuditVerdict,
    /// 0..=100.
    pub trust_score: u32,
    /// `None` while the version is unaudited.
    pub auditor: Option<Address>,
    pub evidence_hash: BytesN<32>,
    /// 0 while the version is unaudited.
    pub audited_at: u64,
}

/// Header entry for a skill: ownership plus the list of registered versions.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SkillEntry {
    pub skill_id: String,
    pub owner: Address,
    /// Versions in registration order.
    pub versions: Vec<String>,
    /// Last version REGISTERED (not necessarily audited).
    pub latest_version: String,
    /// Last version that received a verdict, `None` if none was ever audited.
    pub latest_audited_version: Option<String>,
    pub registered_at: u64,
}

/// Weighted scoring configuration for trust score computation.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TrustScoreConfig {
    /// Weight for description analysis score (0-100).
    pub desc_weight: u32,
    /// Weight for sandbox behavioral score (0-100).
    pub sandbox_weight: u32,
    /// Weight for prior reputation (0-100).
    pub reputation_weight: u32,
}

impl Default for TrustScoreConfig {
    fn default() -> Self {
        TrustScoreConfig {
            desc_weight: 40,
            sandbox_weight: 40,
            reputation_weight: 20,
        }
    }
}

/// Storage keys.
///
/// `Admin` / `Auditor` / `TrustConfig` / `SkillCount` live in instance storage
/// (small, bounded). Everything that grows per skill lives in persistent storage:
/// instance storage is capped at 64KB serialized, so an unbounded `SkillIndex`
/// there (as the scaffold had) would eventually brick the contract.
#[contracttype]
#[derive(Clone, Debug)]
pub enum DataKey {
    /// instance -> Address
    Admin,
    /// instance -> Address
    Auditor,
    /// instance -> TrustScoreConfig
    TrustConfig,
    /// instance -> u32
    SkillCount,
    /// persistent: skill_id -> SkillEntry
    Skill(String),
    /// persistent: (skill_id, version) -> VersionRecord
    Version(String, String),
    /// persistent: content_hash -> (skill_id, version)
    HashIndex(BytesN<32>),
    /// persistent: index -> skill_id
    SkillIndex(u32),
    // --- STE-44, appended. Storage is append-only: an upgrade reinterprets the
    // old bytes with new code, so an existing variant may never be removed,
    // renamed or retyped. New variants go at the end.
    /// instance -> u64, the timelock in SECONDS. Written once by the
    /// constructor; there is deliberately no setter, because an admin who can
    /// shorten the delay has no timelock at all.
    UpgradeDelay,
    /// instance -> PendingUpgrade, present only while a proposal is open.
    PendingUpgrade,
    /// instance -> bool, `true` once upgradeability has been renounced. One-way.
    UpgradeRenounced,
}

/// Typed contract errors. The numbers are part of the public ABI — never renumber.
#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum RegistryError {
    NotInitialized = 1,
    NotAuthorized = 2,
    SkillNotFound = 3,
    VersionNotFound = 4,
    VersionAlreadyExists = 5,
    HashAlreadyRegistered = 6,
    /// Empty skill_id or version.
    InvalidInput = 7,
    /// Trust score > 100.
    InvalidTrustScore = 8,
    /// `submit_verdict` called with `AuditVerdict::Unaudited`.
    InvalidVerdict = 9,
    /// STE-44: `renounce_upgradeability` has been called. Permanent.
    UpgradeabilityRenounced = 10,
    /// `execute_upgrade` / `cancel_upgrade` with nothing proposed.
    NoPendingUpgrade = 11,
    /// `propose_upgrade` while another proposal is still open. Cancel it first,
    /// so that replacing a proposal always costs a visible `UpgradeCancelled`
    /// event and a fresh full delay.
    UpgradeAlreadyPending = 12,
    /// `execute_upgrade` before `ready_at`.
    UpgradeNotReady = 13,
}

/// Emitted the first time a skill_id is seen.
/// topics: ("skill_registered", skill_id)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SkillRegistered {
    #[topic]
    pub skill_id: String,
    pub owner: Address,
}

/// Emitted for every registered version (including the first one).
/// topics: ("version_registered", skill_id, version)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VersionRegistered {
    #[topic]
    pub skill_id: String,
    #[topic]
    pub version: String,
    pub content_hash: BytesN<32>,
    pub owner: Address,
}

/// Handoff contract to the off-chain indexer (STE-13). Do not change its shape.
/// topics: ("version_recorded", skill_id, version)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VersionRecorded {
    #[topic]
    pub skill_id: String,
    #[topic]
    pub version: String,
    pub content_hash: BytesN<32>,
    pub verdict: AuditVerdict,
    pub trust_score: u32,
    pub auditor: Address,
}

/// Emitted only when an already-audited version gets a DIFFERENT verdict.
/// `new` is a Rust keyword, hence the `old_verdict` / `new_verdict` field names.
/// topics: ("verdict_flipped", skill_id, version)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VerdictFlipped {
    #[topic]
    pub skill_id: String,
    #[topic]
    pub version: String,
    pub old_verdict: AuditVerdict,
    pub new_verdict: AuditVerdict,
}

// ---------------------------------------------------------------------------
// STE-44 — upgradeability
// ---------------------------------------------------------------------------

/// Fallback timelock, in seconds, used only when `DataKey::UpgradeDelay` is
/// absent — which can happen exactly once: if some future wasm is upgraded in
/// from a build that predates the key.
///
/// It is deliberately LONGER than any delay we would configure (24h), because a
/// missing field must only ever make the timelock stricter. A `0` fallback would
/// turn a storage miss into "no timelock at all", which is the one outcome this
/// whole mechanism exists to prevent.
pub const FALLBACK_UPGRADE_DELAY: u64 = 86_400;

/// An upgrade that has been announced but not yet performed.
///
/// This is the object outsiders watch. `wasm_hash` is the sha256 of the exact
/// bytes that will replace the contract, so anyone can fetch that wasm, read its
/// interface, diff it, and object — during `ready_at - proposed_at` seconds.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PendingUpgrade {
    /// sha256 of the replacement wasm, i.e. the Soroban wasm hash it was
    /// uploaded under.
    pub wasm_hash: BytesN<32>,
    /// Ledger timestamp at which `propose_upgrade` ran.
    pub proposed_at: u64,
    /// Earliest ledger timestamp at which `execute_upgrade` will be accepted.
    pub ready_at: u64,
}

/// Emitted by `propose_upgrade`. The timelock is only worth something if the
/// clock starts in public, so this event carries both ends of the window.
/// topics: ("upgrade_proposed", wasm_hash)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UpgradeProposed {
    #[topic]
    pub wasm_hash: BytesN<32>,
    pub proposed_at: u64,
    pub ready_at: u64,
}

/// Emitted by `execute_upgrade`, immediately before the wasm is replaced.
/// topics: ("upgrade_executed", wasm_hash)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UpgradeExecuted {
    #[topic]
    pub wasm_hash: BytesN<32>,
    pub executed_at: u64,
}

/// Emitted by `cancel_upgrade`, and by `renounce_upgradeability` when it clears
/// a proposal that was still open.
/// topics: ("upgrade_cancelled", wasm_hash)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UpgradeCancelled {
    #[topic]
    pub wasm_hash: BytesN<32>,
    pub cancelled_at: u64,
}

/// Emitted by `renounce_upgradeability`. There is no counterpart event, because
/// there is no way back.
/// topics: ("upgradeability_renounced",)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UpgradeabilityRenounced {
    pub renounced_at: u64,
    /// The admin that gave the power up, recorded so the act is attributable.
    pub admin: Address,
}
