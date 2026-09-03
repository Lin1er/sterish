#![no_std]

mod data;
mod test;

pub use data::{
    AuditVerdict, DataKey, RegistryError, SkillEntry, SkillRegistered, TrustScoreConfig,
    VerdictFlipped, VersionRecord, VersionRecorded, VersionRegistered,
};
use data::{BUMP_THRESHOLD, BUMP_TO};
use soroban_sdk::{contract, contractimpl, Address, Env};

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
