#![no_std]

mod data;
mod test;

pub use data::{
    AuditRequest, AuditStatus, BondPosted, EscrowError, RequestCreated, Settled, Slashed,
    StorageKey,
};
use data::{BUMP_THRESHOLD, BUMP_TO};
use soroban_sdk::{contract, contractimpl, Address, Env};

#[contract]
pub struct UsdcEscrow;

/// Bump the instance entry (token/admin/counter) on every write.
fn bump_instance(env: &Env) {
    env.storage().instance().extend_ttl(BUMP_THRESHOLD, BUMP_TO);
}

#[contractimpl]
impl UsdcEscrow {
    /// Constructor — runs atomically at deploy time. The scaffold's `initialize`
    /// left a deploy->initialize window in which anyone could claim admin.
    pub fn __constructor(env: Env, usdc_token: Address, admin: Address) {
        env.storage()
            .instance()
            .set(&StorageKey::UsdcToken, &usdc_token);
        env.storage().instance().set(&StorageKey::Admin, &admin);
        env.storage()
            .instance()
            .set(&StorageKey::NextRequestId, &1u32);
        bump_instance(&env);
    }

    /// Read one job.
    pub fn get_request(env: Env, request_id: u32) -> Result<AuditRequest, EscrowError> {
        env.storage()
            .persistent()
            .get(&StorageKey::Request(request_id))
            .ok_or(EscrowError::RequestNotFound)
    }

    /// Address of the USDC SAC this escrow settles in.
    pub fn get_usdc_token(env: Env) -> Result<Address, EscrowError> {
        env.storage()
            .instance()
            .get(&StorageKey::UsdcToken)
            .ok_or(EscrowError::NotInitialized)
    }

    /// Address allowed to `settle` / `slash` / `claim_forfeited`.
    pub fn get_admin(env: Env) -> Result<Address, EscrowError> {
        env.storage()
            .instance()
            .get(&StorageKey::Admin)
            .ok_or(EscrowError::NotInitialized)
    }

    /// Number of jobs ever created. Derived from `NextRequestId` so there is no
    /// second counter to drift out of sync.
    pub fn get_request_count(env: Env) -> u32 {
        env.storage()
            .instance()
            .get::<StorageKey, u32>(&StorageKey::NextRequestId)
            .unwrap_or(1u32)
            .saturating_sub(1)
    }
}
