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

    /// Submit an audit verdict for ONE specific version. Auditor only.
    ///
    /// The verdict is stored on the `VersionRecord`, never on the skill header, so
    /// auditing v1 says nothing about v2.
    pub fn submit_verdict(
        env: Env,
        skill_id: String,
        version: String,
        verdict: AuditVerdict,
        score: u32,
        evidence_hash: BytesN<32>,
    ) -> Result<(), RegistryError> {
        let auditor = Self::get_auditor(env.clone())?;
        auditor.require_auth();

        // Hard failure instead of the scaffold's silent clamp: a corrupted score is
        // worse than a rejected transaction.
        if score > 100 {
            return Err(RegistryError::InvalidTrustScore);
        }
        if verdict == AuditVerdict::Unaudited {
            return Err(RegistryError::InvalidVerdict);
        }

        let skill_key = DataKey::Skill(skill_id.clone());
        let version_key = DataKey::Version(skill_id.clone(), version.clone());

        let mut entry: SkillEntry = env
            .storage()
            .persistent()
            .get(&skill_key)
            .ok_or(RegistryError::SkillNotFound)?;
        let mut record: VersionRecord = env
            .storage()
            .persistent()
            .get(&version_key)
            .ok_or(RegistryError::VersionNotFound)?;

        let old_verdict = record.verdict.clone();

        record.verdict = verdict.clone();
        record.trust_score = score;
        record.auditor = Some(auditor.clone());
        record.evidence_hash = evidence_hash;
        record.audited_at = env.ledger().timestamp();

        entry.latest_audited_version = Some(version.clone());

        env.storage().persistent().set(&version_key, &record);
        env.storage().persistent().set(&skill_key, &entry);

        bump_persistent(&env, &version_key);
        bump_persistent(&env, &skill_key);
        bump_instance(&env);

        if old_verdict != AuditVerdict::Unaudited && old_verdict != verdict {
            VerdictFlipped {
                skill_id: skill_id.clone(),
                version: version.clone(),
                old_verdict,
                new_verdict: verdict.clone(),
            }
            .publish(&env);
        }

        VersionRecorded {
            skill_id,
            version,
            content_hash: record.content_hash,
            verdict,
            trust_score: score,
            auditor,
        }
        .publish(&env);

        Ok(())
    }

    /// Resolve a content hash to the exact version it belongs to.
    ///
    /// A miss returns `None` (never panics): an agent that flips a single byte of an
    /// audited artifact gets "unknown", not the audited version's badge.
    pub fn lookup_by_hash(env: Env, content_hash: BytesN<32>) -> Option<VersionRecord> {
        let (skill_id, version): (String, String) = env
            .storage()
            .persistent()
            .get(&DataKey::HashIndex(content_hash))?;
        env.storage()
            .persistent()
            .get(&DataKey::Version(skill_id, version))
    }

    /// Read one specific version record.
    pub fn get_version(
        env: Env,
        skill_id: String,
        version: String,
    ) -> Result<VersionRecord, RegistryError> {
        if !env
            .storage()
            .persistent()
            .has(&DataKey::Skill(skill_id.clone()))
        {
            return Err(RegistryError::SkillNotFound);
        }
        env.storage()
            .persistent()
            .get(&DataKey::Version(skill_id, version))
            .ok_or(RegistryError::VersionNotFound)
    }

    /// Read the record of the most recently REGISTERED version (audited or not).
    pub fn get_latest(env: Env, skill_id: String) -> Result<VersionRecord, RegistryError> {
        let entry: SkillEntry = env
            .storage()
            .persistent()
            .get(&DataKey::Skill(skill_id.clone()))
            .ok_or(RegistryError::SkillNotFound)?;
        env.storage()
            .persistent()
            .get(&DataKey::Version(skill_id, entry.latest_version))
            .ok_or(RegistryError::VersionNotFound)
    }

    /// True only when THIS version was audited `Safe`. Unknown skill/version is
    /// `false`, never a panic — this is the gate for minting the VERIFIED badge.
    pub fn is_verified(env: Env, skill_id: String, version: String) -> bool {
        match env
            .storage()
            .persistent()
            .get::<DataKey, VersionRecord>(&DataKey::Version(skill_id, version))
        {
            Some(record) => record.verdict == AuditVerdict::Safe,
            None => false,
        }
    }

    /// Query a single skill header by ID.
    pub fn query_skill(env: Env, skill_id: String) -> Result<SkillEntry, RegistryError> {
        env.storage()
            .persistent()
            .get(&DataKey::Skill(skill_id))
            .ok_or(RegistryError::SkillNotFound)
    }

    /// Query a paginated list of registered skill headers.
    pub fn query_all_skills(env: Env, start: u32, limit: u32) -> Vec<SkillEntry> {
        let count = Self::get_skill_count(env.clone());
        let end = core::cmp::min(start.saturating_add(limit), count);

        let mut results = Vec::new(&env);
        let mut i = start;
        while i < end {
            if let Some(id) = env
                .storage()
                .persistent()
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
