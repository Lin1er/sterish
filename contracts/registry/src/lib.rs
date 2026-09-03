#![no_std]

mod data;
mod test;

pub use data::{
    AuditVerdict, DataKey, RegistryError, SkillEntry, SkillRegistered, TrustScoreConfig,
    VerdictFlipped, VersionRecord, VersionRecorded, VersionRegistered,
};
use data::{BUMP_THRESHOLD, BUMP_TO};
use soroban_sdk::{contract, contractimpl, Address, BytesN, Env, String, Vec};

#[contract]
pub struct SkillRegistry;

/// Bump the instance entry (admin/auditor/config/count) on every write.
fn bump_instance(env: &Env) {
    env.storage().instance().extend_ttl(BUMP_THRESHOLD, BUMP_TO);
}

/// Bump one persistent entry. `extend_ttl` is a floor-only no-op when the current
/// TTL is already >= threshold, so calling it on every write is safe and cheap.
fn bump_persistent(env: &Env, key: &DataKey) {
    env.storage()
        .persistent()
        .extend_ttl(key, BUMP_THRESHOLD, BUMP_TO);
}

#[contractimpl]
impl SkillRegistry {
    /// Constructor — runs atomically at deploy time, so there is no deploy->initialize
    /// window for anyone to front-run (that was the `initialize` pattern's weakness).
    pub fn __constructor(env: Env, admin: Address, auditor: Address) {
        env.storage().instance().set(&DataKey::Admin, &admin);
        env.storage().instance().set(&DataKey::Auditor, &auditor);
        env.storage()
            .instance()
            .set(&DataKey::TrustConfig, &TrustScoreConfig::default());
        env.storage().instance().set(&DataKey::SkillCount, &0u32);
        bump_instance(&env);
    }

    /// Register a new version of a skill.
    ///
    /// `owner` must authorize the call. The scaffold used
    /// `env.current_contract_address()` as the creator with no auth at all, which let
    /// anyone register anything under any identity — that is the main bug fixed here.
    ///
    /// Invariants enforced:
    /// - a skill_id belongs to exactly one owner; only that owner can add versions;
    /// - a (skill_id, version) pair is immutable — it can never be overwritten;
    /// - a content_hash maps to exactly one (skill_id, version), so `lookup_by_hash`
    ///   is never ambiguous and hash-squatting is impossible.
    pub fn register_skill(
        env: Env,
        owner: Address,
        skill_id: String,
        version: String,
        content_hash: BytesN<32>,
    ) -> Result<(), RegistryError> {
        owner.require_auth();

        if skill_id.is_empty() || version.is_empty() {
            return Err(RegistryError::InvalidInput);
        }

        let skill_key = DataKey::Skill(skill_id.clone());
        let version_key = DataKey::Version(skill_id.clone(), version.clone());
        let hash_key = DataKey::HashIndex(content_hash.clone());

        let existing: Option<SkillEntry> = env.storage().persistent().get(&skill_key);
        if let Some(ref entry) = existing {
            if entry.owner != owner {
                return Err(RegistryError::NotAuthorized);
            }
        }
        if env.storage().persistent().has(&version_key) {
            return Err(RegistryError::VersionAlreadyExists);
        }
        if env.storage().persistent().has(&hash_key) {
            return Err(RegistryError::HashAlreadyRegistered);
        }

        let now = env.ledger().timestamp();

        let mut entry = match existing {
            Some(entry) => entry,
            None => {
                let count = Self::get_skill_count(env.clone());
                let index_key = DataKey::SkillIndex(count);
                env.storage().persistent().set(&index_key, &skill_id);
                bump_persistent(&env, &index_key);
                env.storage()
                    .instance()
                    .set(&DataKey::SkillCount, &(count + 1));

                SkillRegistered {
                    skill_id: skill_id.clone(),
                    owner: owner.clone(),
                }
                .publish(&env);

                SkillEntry {
                    skill_id: skill_id.clone(),
                    owner: owner.clone(),
                    versions: Vec::new(&env),
                    latest_version: version.clone(),
                    latest_audited_version: None,
                    registered_at: now,
                }
            }
        };

        let record = VersionRecord {
            skill_id: skill_id.clone(),
            version: version.clone(),
            content_hash: content_hash.clone(),
            owner: owner.clone(),
            registered_at: now,
            verdict: AuditVerdict::Unaudited,
            trust_score: 0,
            auditor: None,
            evidence_hash: BytesN::from_array(&env, &[0u8; 32]),
            audited_at: 0,
        };

        entry.versions.push_back(version.clone());
        entry.latest_version = version.clone();

        env.storage().persistent().set(&version_key, &record);
        env.storage().persistent().set(&skill_key, &entry);
        env.storage()
            .persistent()
            .set(&hash_key, &(skill_id.clone(), version.clone()));

        bump_persistent(&env, &version_key);
        bump_persistent(&env, &skill_key);
        bump_persistent(&env, &hash_key);
        bump_instance(&env);

        VersionRegistered {
            skill_id,
            version,
            content_hash,
            owner,
        }
        .publish(&env);

        Ok(())
    }

    /// Set the authorized auditor address. Admin only.
    pub fn set_auditor(env: Env, auditor: Address) -> Result<(), RegistryError> {
        let admin = Self::get_admin(env.clone())?;
        admin.require_auth();
        env.storage().instance().set(&DataKey::Auditor, &auditor);
        bump_instance(&env);
        Ok(())
    }

    /// Update the trust score configuration. Admin only.
    pub fn update_trust_score_config(
        env: Env,
        config: TrustScoreConfig,
    ) -> Result<(), RegistryError> {
        let admin = Self::get_admin(env.clone())?;
        admin.require_auth();
        env.storage().instance().set(&DataKey::TrustConfig, &config);
        bump_instance(&env);
        Ok(())
    }

    /// Read the current trust score config.
    pub fn get_trust_score_config(env: Env) -> TrustScoreConfig {
        env.storage()
            .instance()
            .get(&DataKey::TrustConfig)
            .unwrap_or_default()
    }

    /// Read the current auditor address.
    pub fn get_auditor(env: Env) -> Result<Address, RegistryError> {
        env.storage()
            .instance()
            .get(&DataKey::Auditor)
            .ok_or(RegistryError::NotInitialized)
    }

    /// Read the admin address.
    pub fn get_admin(env: Env) -> Result<Address, RegistryError> {
        env.storage()
            .instance()
            .get(&DataKey::Admin)
            .ok_or(RegistryError::NotInitialized)
    }

    /// Number of distinct skills registered.
    pub fn get_skill_count(env: Env) -> u32 {
        env.storage()
            .instance()
            .get(&DataKey::SkillCount)
            .unwrap_or(0u32)
    }
}
