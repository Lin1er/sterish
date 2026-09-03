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
