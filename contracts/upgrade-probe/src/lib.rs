#![no_std]
//! STE-44 test fixture — a stand-in "v2" for the `SkillRegistry`.
//!
//! This is what `contracts/tests/tests/upgrade.rs` upgrades the registry INTO.
//! It is not a product contract and is never deployed; it is the smallest thing
//! that can answer three questions a native test `Env` cannot:
//!
//! 1. **Does storage really survive?** `get_skill_count` and `get_admin` read
//!    the registry's own keys. If the swap corrupted state, or if Soroban keyed
//!    storage by declaration order rather than by variant name, these would come
//!    back wrong.
//! 2. **Does new code really take effect?** `probe_version` does not exist in the
//!    registry at all, so a call to it succeeding is proof the wasm changed.
//! 3. **Can a new field be initialised after the fact?** `MigratedAt` is a key
//!    the registry never had. The constructor does NOT re-run on upgrade, so the
//!    only way to fill it is `migrate` — the migration path the real contracts
//!    will need the day they add a field.
//!
//! Because only its WASM is ever executed, this crate reports 0% native line
//! coverage in `cargo llvm-cov`. That is not a gap — there is no native code
//! path to cover — and it is left visible rather than excluded, because a
//! coverage table that quietly omits rows is worth less than one that does not.
//!
//! The `DataKey` variants below deliberately repeat the registry's spelling.
//! Soroban encodes a `#[contracttype]` unit variant as its NAME, not its index,
//! so matching names is what makes the old entries readable — and renaming one
//! is what would silently orphan them.

mod upgrade;

use soroban_sdk::{
    contract, contracterror, contractimpl, contracttype, Address, BytesN, Env, String, Val,
};

/// Only the registry keys this fixture touches, plus the one it adds.
#[contracttype]
#[derive(Clone, Debug)]
pub enum DataKey {
    /// Written by the registry's constructor. Must read back unchanged.
    Admin,
    /// Written by the registry's constructor.
    Auditor,
    /// Advanced by the registry's `register_skill`. Must read back unchanged.
    SkillCount,
    /// The registry's upgrade timelock, carried across untouched.
    UpgradeDelay,
    PendingUpgrade,
    UpgradeRenounced,
    /// persistent: index -> skill_id, written by the registry's `register_skill`.
    SkillIndex(u32),
    /// persistent: content_hash -> (skill_id, version), likewise.
    HashIndex(BytesN<32>),
    /// NEW in this version. Absent in every entry the registry wrote, which is
    /// exactly the situation a real migration faces.
    MigratedAt,
}

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum ProbeError {
    NotInitialized = 1,
    /// Kept at the registry's number so a caller cannot tell the two apart by
    /// error code alone — the fixture must not be accidentally "nicer" than the
    /// thing it stands in for.
    UpgradeabilityRenounced = 10,
    NoPendingUpgrade = 11,
    UpgradeAlreadyPending = 12,
    UpgradeNotReady = 13,
    /// `migrate` called twice. A migration that can run again is a migration
    /// that can be replayed against state it has already touched.
    AlreadyMigrated = 20,
}

/// An upgrade that has been announced but not yet performed. Field-for-field the
/// registry's `PendingUpgrade`, so the entry written by the old code decodes
/// under the new code.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PendingUpgrade {
    pub wasm_hash: BytesN<32>,
    pub proposed_at: u64,
    pub ready_at: u64,
}

#[contract]
pub struct UpgradeProbe;

#[contractimpl]
impl UpgradeProbe {
    /// Present so the fixture can also be deployed on its own. It does NOT run
    /// when the registry is upgraded into this wasm — that is the whole point of
    /// `migrate`.
    pub fn __constructor(env: Env, admin: Address, auditor: Address, upgrade_delay_secs: u64) {
        env.storage().instance().set(&DataKey::Admin, &admin);
        env.storage().instance().set(&DataKey::Auditor, &auditor);
        env.storage().instance().set(&DataKey::SkillCount, &0u32);
        env.storage()
            .instance()
            .set(&DataKey::UpgradeDelay, &upgrade_delay_secs);
    }

    /// The function that does not exist in the registry. Calling it is the proof
    /// that the deployed code changed.
    pub fn probe_version(_env: Env) -> u32 {
        2
    }

    /// Initialise the field this version added. Admin only, and only once.
    pub fn migrate(env: Env, migrated_at: u64) -> Result<(), ProbeError> {
        let admin = Self::get_admin(env.clone())?;
        admin.require_auth();
        if env.storage().instance().has(&DataKey::MigratedAt) {
            return Err(ProbeError::AlreadyMigrated);
        }
        env.storage()
            .instance()
            .set(&DataKey::MigratedAt, &migrated_at);
        Ok(())
    }

    pub fn get_migrated_at(env: Env) -> Option<u64> {
        env.storage().instance().get(&DataKey::MigratedAt)
    }

    /// Reads the key the OLD contract wrote.
    pub fn get_admin(env: Env) -> Result<Address, ProbeError> {
        env.storage()
            .instance()
            .get(&DataKey::Admin)
            .ok_or(ProbeError::NotInitialized)
    }

    /// Reads the counter the OLD contract advanced.
    pub fn get_skill_count(env: Env) -> u32 {
        env.storage()
            .instance()
            .get(&DataKey::SkillCount)
            .unwrap_or(0u32)
    }

    /// Reads PERSISTENT state written by the old contract, through a key variant
    /// that carries a payload. Instance storage surviving is the easy half; this
    /// is the half that would break if a key variant were reordered or retyped.
    pub fn get_skill_index(env: Env, index: u32) -> Option<String> {
        env.storage().persistent().get(&DataKey::SkillIndex(index))
    }

    /// Same, for a `BytesN<32>`-keyed entry holding a TUPLE value — the shape
    /// most likely to decode wrongly if anything about the encoding drifted.
    pub fn lookup_hash(env: Env, content_hash: BytesN<32>) -> Option<(String, String)> {
        env.storage()
            .persistent()
            .get(&DataKey::HashIndex(content_hash))
    }
}

/// Wraps `execute_upgrade` and `migrate` into ONE invocation.
///
/// It shares this crate — and therefore this wasm — with `UpgradeProbe`, so the
/// built artifact exports both contracts' entrypoints and is deployed twice, at
/// two addresses, in the tests. That is fine for a fixture and would not be for
/// a product contract.
///
/// The new implementation only takes effect after the current invocation ends,
/// so a contract cannot upgrade itself and then call its own new migration in
/// the same call. An auxiliary contract can, because from its point of view the
/// two are separate invocations of somebody else. This is the pattern the
/// OpenZeppelin `Upgrader` uses, hand-rolled here for the same reason the rest
/// of this ticket is.
#[contract]
pub struct Upgrader;

#[contractimpl]
impl Upgrader {
    pub fn upgrade_and_migrate(
        env: Env,
        contract_address: Address,
        operator: Address,
        migration_args: soroban_sdk::Vec<Val>,
    ) {
        operator.require_auth();
        // `execute_upgrade` is 15 characters, past what `symbol_short!` accepts.
        env.invoke_contract::<()>(
            &contract_address,
            &soroban_sdk::Symbol::new(&env, "execute_upgrade"),
            soroban_sdk::Vec::new(&env),
        );
        env.invoke_contract::<()>(
            &contract_address,
            &soroban_sdk::Symbol::new(&env, "migrate"),
            migration_args,
        );
    }
}
