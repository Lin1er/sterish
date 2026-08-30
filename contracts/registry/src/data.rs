use soroban_sdk::{contracttype, Address, BytesN, String, Vec};

/// A single version of a registered skill.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SkillVersion {
    pub version: String,
    pub content_hash: BytesN<32>,
    pub creator: Address,
    pub registered_at: u64,
}

/// Audit verdict for a skill.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AuditVerdict {
    Unaudited,
    Safe,
    Dangerous,
    Warning,
}

impl Default for AuditVerdict {
    fn default() -> Self {
        AuditVerdict::Unaudited
    }
}

/// Full on-chain entry for a skill.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SkillEntry {
    pub skill_id: String,
    pub versions: Vec<SkillVersion>,
    pub latest_verdict: AuditVerdict,
    pub trust_score: u32,
    pub auditor: Address,
    pub evidence_hash: BytesN<32>,
    pub audit_timestamp: u64,
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

/// Storage keys used by the contract.
#[contracttype]
#[derive(Clone, Debug)]
pub enum DataKey {
    Skill(String),
    Auditor,
    TrustConfig,
    Admin,
    SkillCount,
    SkillIndex(u32),
}
