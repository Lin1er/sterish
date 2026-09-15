//! STE-44 — the registry's upgrade path: a two-step timelock with events, and a
//! permanent off switch.
//!
//! # Why this exists at all, and why it is uncomfortable
//!
//! Sterish sells verdicts that cannot be forged. An admin who can replace this
//! contract's wasm can change what `is_verified` means, retroactively, for every
//! version already on chain — and the value of "on-chain proof" then rests on
//! that admin choosing not to. That tension is real and is not resolved by
//! wishing; it is bounded by exactly two things, both implemented here:
//!
//! 1. **It cannot be done silently.** `propose_upgrade` publishes the wasm hash
//!    and starts a clock that the admin cannot shorten. Anyone watching the
//!    contract's events sees the replacement bytes, can fetch and read them, and
//!    has the whole delay to react. A timelock without events is just a delay
//!    nobody can observe, so the events are load-bearing, not decoration.
//! 2. **It can be switched off forever.** `renounce_upgradeability` is one-way.
//!    Once the verdict rules stabilise, the admin can give the power up and the
//!    contract becomes as immutable as one that never had an upgrade function.
//!
//! See `docs/SYSTEM_DESIGN.md` §"Upgradeability" for the same argument written
//! out for a reader who is not holding the code.
//!
//! # Why this is hand-rolled rather than OpenZeppelin
//!
//! Measured, not assumed, on 2026-09-15: `stellar-contract-utils` 0.7.2 — the
//! latest release, 2026-06-09 — declares `soroban-sdk ^26.1.0`. This workspace is
//! pinned to 27.0.6, and `^26.1.0` does not admit 27.x, so a real resolution
//! produces TWO copies of soroban-sdk (26.1.1 and 27.0.6) whose `Env` and
//! `Address` are mutually incompatible types. That is the same wall the tokens
//! contract hit with the OZ non-fungible module (see `contracts/tokens/src/lib.rs`).
//! The `Upgradeable` derive macro is ~30 lines of machinery; this file is that,
//! plus the timelock and the off switch the macro does not provide.
//!
//! # Access control
//!
//! Every mutating entrypoint here authorizes against the stored admin `Address`
//! and nothing else — no role system, no governance contract.
//!
//! The admin is a single Stellar account today. Going 2-of-3 later needs **no
//! contract change**: multisig on Stellar is a property of the *account*, not of
//! the contract, so the contract keeps storing one `Address` and keeps calling
//! `require_auth()`, and the upgrade to a 2-of-3 is a `Set Options` transaction
//! on that account. Nobody should ever migrate this contract for that reason.

use crate::{
    bump_instance,
    data::{
        DataKey, PendingUpgrade, RegistryError, UpgradeCancelled, UpgradeExecuted, UpgradeProposed,
        UpgradeabilityRenounced, FALLBACK_UPGRADE_DELAY,
    },
    SkillRegistry,
};
// `#[contractimpl]` expands into impls on the generated client and args types, so
// a second impl block in another module has to name them even though this file
// never writes them itself.
#[allow(unused_imports)]
use crate::{SkillRegistryArgs, SkillRegistryClient};
use soroban_sdk::{contractimpl, BytesN, Env};

/// Load the admin and require its authorization, after refusing outright if
/// upgradeability has been renounced.
///
/// The renounce check comes FIRST on purpose: after renouncing there is no
/// privileged upgrade caller at all, so answering "not authorized" to the admin
/// would be the wrong story. The contract is not guarding a door; the door is
/// gone.
fn require_upgrade_admin(env: &Env) -> Result<soroban_sdk::Address, RegistryError> {
    if SkillRegistry::is_upgrade_renounced(env) {
        return Err(RegistryError::UpgradeabilityRenounced);
    }
    let admin = SkillRegistry::get_admin(env.clone())?;
    admin.require_auth();
    Ok(admin)
}

#[contractimpl]
impl SkillRegistry {
    /// Announce an upgrade to `wasm_hash` and start the timelock. Admin only.
    ///
    /// Returns the `ready_at` timestamp, so the caller does not have to re-read
    /// state to learn when the window opens.
    ///
    /// `wasm_hash` is the sha256 the replacement wasm was uploaded under. It is
    /// NOT checked to exist: `update_current_contract_wasm` fails at execute time
    /// if it does not, and refusing to accept a hash before its upload would only
    /// force the admin to reveal the bytes in a different order.
    ///
    /// A second proposal while one is open is REJECTED rather than allowed to
    /// overwrite. Overwriting would let an admin publish a benign wasm, wait out
    /// the delay in public, then swap in different bytes just before executing —
    /// the timelock would be on the announcement, not on the code. Requiring
    /// `cancel_upgrade` first means every replacement costs a visible
    /// `UpgradeCancelled` event and a fresh, full delay.
    pub fn propose_upgrade(env: Env, wasm_hash: BytesN<32>) -> Result<u64, RegistryError> {
        require_upgrade_admin(&env)?;

        if env.storage().instance().has(&DataKey::PendingUpgrade) {
            return Err(RegistryError::UpgradeAlreadyPending);
        }

        let proposed_at = env.ledger().timestamp();
        let ready_at = proposed_at.saturating_add(Self::get_upgrade_delay(env.clone()));

        let pending = PendingUpgrade {
            wasm_hash: wasm_hash.clone(),
            proposed_at,
            ready_at,
        };
        env.storage()
            .instance()
            .set(&DataKey::PendingUpgrade, &pending);
        bump_instance(&env);

        UpgradeProposed {
            wasm_hash,
            proposed_at,
            ready_at,
        }
        .publish(&env);

        Ok(ready_at)
    }

    /// Replace this contract's wasm with the proposed one. Admin only, and only
    /// once `ready_at` has passed.
    ///
    /// The new code takes effect only AFTER this invocation returns, which is why
    /// nothing here can call into it — including any migration the new version
    /// needs. See the module docs of `contracts/tests/tests/upgrade.rs` for the
    /// `Upgrader` wrapper that makes upgrade+migrate atomic when that is required.
    ///
    /// The pending proposal is cleared BEFORE the swap, so the incoming code can
    /// never find a stale proposal in its storage and re-execute it.
    pub fn execute_upgrade(env: Env) -> Result<(), RegistryError> {
        require_upgrade_admin(&env)?;

        let pending: PendingUpgrade = env
            .storage()
            .instance()
            .get(&DataKey::PendingUpgrade)
            .ok_or(RegistryError::NoPendingUpgrade)?;

        let now = env.ledger().timestamp();
        if now < pending.ready_at {
            return Err(RegistryError::UpgradeNotReady);
        }

        env.storage().instance().remove(&DataKey::PendingUpgrade);
        bump_instance(&env);

        UpgradeExecuted {
            wasm_hash: pending.wasm_hash.clone(),
            executed_at: now,
        }
        .publish(&env);

        env.deployer()
            .update_current_contract_wasm(pending.wasm_hash);
        Ok(())
    }

    /// Withdraw an open proposal. Admin only.
    pub fn cancel_upgrade(env: Env) -> Result<(), RegistryError> {
        require_upgrade_admin(&env)?;

        let pending: PendingUpgrade = env
            .storage()
            .instance()
            .get(&DataKey::PendingUpgrade)
            .ok_or(RegistryError::NoPendingUpgrade)?;

        env.storage().instance().remove(&DataKey::PendingUpgrade);
        bump_instance(&env);

        UpgradeCancelled {
            wasm_hash: pending.wasm_hash,
            cancelled_at: env.ledger().timestamp(),
        }
        .publish(&env);

        Ok(())
    }

    /// Give up the ability to upgrade this contract. Admin only. **Permanent.**
    ///
    /// This is the answer to "what stops you rewriting the verdict rules later":
    /// nothing, until this is called — and nothing at all, after. There is no
    /// un-renounce, by construction: the flag is only ever written `true`, and no
    /// entrypoint reads it as anything but a refusal.
    ///
    /// Any open proposal is cancelled in the same call, and that cancellation is
    /// emitted, so a watcher never sees a proposal simply stop existing.
    pub fn renounce_upgradeability(env: Env) -> Result<(), RegistryError> {
        let admin = require_upgrade_admin(&env)?;
        let now = env.ledger().timestamp();

        if let Some(pending) = env
            .storage()
            .instance()
            .get::<DataKey, PendingUpgrade>(&DataKey::PendingUpgrade)
        {
            env.storage().instance().remove(&DataKey::PendingUpgrade);
            UpgradeCancelled {
                wasm_hash: pending.wasm_hash,
                cancelled_at: now,
            }
            .publish(&env);
        }

        env.storage()
            .instance()
            .set(&DataKey::UpgradeRenounced, &true);
        bump_instance(&env);

        UpgradeabilityRenounced {
            renounced_at: now,
            admin,
        }
        .publish(&env);

        Ok(())
    }

    /// The open proposal, or `None`. Never panics — this is what a watcher polls.
    pub fn get_pending_upgrade(env: Env) -> Option<PendingUpgrade> {
        env.storage().instance().get(&DataKey::PendingUpgrade)
    }

    /// The configured timelock in seconds.
    ///
    /// Falls back to [`FALLBACK_UPGRADE_DELAY`] when the key is absent, so a
    /// storage miss can only ever make the timelock longer.
    pub fn get_upgrade_delay(env: Env) -> u64 {
        env.storage()
            .instance()
            .get(&DataKey::UpgradeDelay)
            .unwrap_or(FALLBACK_UPGRADE_DELAY)
    }

    /// `false` once `renounce_upgradeability` has been called.
    pub fn is_upgradeable(env: Env) -> bool {
        !Self::is_upgrade_renounced(&env)
    }
}

impl SkillRegistry {
    /// Internal read of the one-way renounce flag. Not an entrypoint: the public
    /// surface is `is_upgradeable`, phrased the way a caller thinks about it.
    fn is_upgrade_renounced(env: &Env) -> bool {
        env.storage()
            .instance()
            .get(&DataKey::UpgradeRenounced)
            .unwrap_or(false)
    }
}
