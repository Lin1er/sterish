#![no_std]

mod data;
mod test;

use data::{
    AuditVerdict, DataKey, SkillEntry, SkillVersion, TrustScoreConfig,
};
use soroban_sdk::{
    contract, contractimpl, symbol_short, Address, BytesN, Env, String, Vec,
};

#[contract]
pub struct SkillRegistry;

#[contractimpl]
impl SkillRegistry {
    /// Initialize the contract. Sets the admin and optionally the auditor.
    /// Must be called once after deployment.
    pub fn initialize(env: Env, admin: Address, auditor: Address) {
        if env.storage().instance().has(&DataKey::Admin) {
            panic!("already initialized");
        }
        admin.require_auth();
        env.storage().instance().set(&DataKey::Admin, &admin);
        env.storage().instance().set(&DataKey::Auditor, &auditor);
        env.storage()
            .instance()
            .set(&DataKey::TrustConfig, &TrustScoreConfig::default());
        env.storage().instance().set(&DataKey::SkillCount, &0u32);
    }

    /// Register a new version of a skill.
    pub fn register_skill(
        env: Env,
        skill_id: String,
        version: String,
        content_hash: BytesN<32>,
    ) {
        let caller = env.current_contract_address();
        // Read existing entry or create a new one.
        let mut entry: SkillEntry = if env.storage().persistent().has(&DataKey::Skill(skill_id.clone())) {
            env.storage()
                .persistent()
                .get(&DataKey::Skill(skill_id.clone()))
                .unwrap()
        } else {
            // New skill — increment count and store index.
            let count: u32 = env
                .storage()
                .instance()
                .get(&DataKey::SkillCount)
                .unwrap_or(0u32);
            env.storage()
                .instance()
                .set(&DataKey::SkillIndex(count), &skill_id.clone());
            env.storage().instance().set(&DataKey::SkillCount, &(count + 1));

            SkillEntry {
                skill_id: skill_id.clone(),
                versions: Vec::new(&env),
                latest_verdict: AuditVerdict::Unaudited,
                trust_score: 0,
                auditor: caller.clone(),
                evidence_hash: BytesN::from_array(&env, &[0u8; 32]),
                audit_timestamp: 0,
            }
        };

        let new_version = SkillVersion {
            version: version.clone(),
            content_hash,
            creator: caller,
            registered_at: env.ledger().timestamp(),
        };
        entry.versions.push_back(new_version);

        env.storage()
            .persistent()
            .set(&DataKey::Skill(skill_id), &entry);
    }

    /// Submit an audit verdict. Only the authorized auditor may call this.
    pub fn submit_verdict(
        env: Env,
        skill_id: String,
        verdict: AuditVerdict,
        score: u32,
        evidence_hash: BytesN<32>,
    ) {
        let auditor: Address = env
            .storage()
            .instance()
            .get(&DataKey::Auditor)
            .unwrap_or_else(|| panic!("auditor not set"));
        auditor.require_auth();

        let mut entry: SkillEntry = env
            .storage()
            .persistent()
            .get(&DataKey::Skill(skill_id.clone()))
            .unwrap_or_else(|| panic!("skill not found"));

        let clamped_score = if score > 100 { 100 } else { score };

        entry.latest_verdict = verdict;
        entry.trust_score = clamped_score;
        entry.auditor = auditor;
        entry.evidence_hash = evidence_hash;
        entry.audit_timestamp = env.ledger().timestamp();

        env.storage()
            .persistent()
            .set(&DataKey::Skill(skill_id), &entry);
    }

    /// Query a single skill by ID.
    pub fn query_skill(env: Env, skill_id: String) -> SkillEntry {
        env.storage()
            .persistent()
            .get(&DataKey::Skill(skill_id))
            .unwrap_or_else(|| panic!("skill not found"))
    }

    /// Query a paginated list of all registered skills.
    pub fn query_all_skills(env: Env, start: u32, limit: u32) -> Vec<SkillEntry> {
        let count: u32 = env
            .storage()
            .instance()
            .get(&DataKey::SkillCount)
            .unwrap_or(0u32);
        let end = if start.saturating_add(limit) > count {
            count
        } else {
            start.saturating_add(limit)
        };

        let mut results = Vec::new(&env);
        let mut i = start;
        while i < end {
            if let Some(id) = env
                .storage()
                .instance()
                .get::<DataKey, String>(&DataKey::SkillIndex(i))
            {
                if let Some(entry) = env
                    .storage()
                    .persistent()
                    .get::<DataKey, SkillEntry>(&DataKey::Skill(id))
                {
                    results.push_back(entry);
                }
            }
            i += 1;
        }
        results
    }

    /// Set the authorized auditor address. Admin only.
    pub fn set_auditor(env: Env, auditor: Address) {
        let admin: Address = env
            .storage()
            .instance()
            .get(&DataKey::Admin)
            .unwrap_or_else(|| panic!("not initialized"));
        admin.require_auth();
        env.storage().instance().set(&DataKey::Auditor, &auditor);
    }

    /// Update the trust score configuration. Admin only.
    pub fn update_trust_score_config(env: Env, config: TrustScoreConfig) {
        let admin: Address = env
            .storage()
            .instance()
            .get(&DataKey::Admin)
            .unwrap_or_else(|| panic!("not initialized"));
        admin.require_auth();
        env.storage().instance().set(&DataKey::TrustConfig, &config);
    }

    /// Read the current trust score config.
    pub fn get_trust_score_config(env: Env) -> TrustScoreConfig {
        env.storage()
            .instance()
            .get(&DataKey::TrustConfig)
            .unwrap_or_else(TrustScoreConfig::default)
    }

    /// Read the current auditor address.
    pub fn get_auditor(env: Env) -> Address {
        env.storage()
            .instance()
            .get(&DataKey::Auditor)
            .unwrap_or_else(|| panic!("auditor not set"))
    }
}
