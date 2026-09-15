//! STE-44 test fixture — the same upgrade machinery the registry ships.
//!
//! Derived from `contracts/registry/src/upgrade.rs` so the fixture cannot
//! quietly behave better than the thing it stands in for: the point of upgrading
//! the registry INTO this wasm is to show that upgradeability survives the swap,
//! and it only shows that if the machinery on the other side is the same
//! machinery.

use crate::{DataKey, PendingUpgrade, ProbeError, UpgradeProbe};
#[allow(unused_imports)]
use crate::{UpgradeProbeArgs, UpgradeProbeClient};
use soroban_sdk::{contractevent, contractimpl, Address, BytesN, Env};

/// Fallback timelock, in seconds, matching the registry's.
pub const FALLBACK_UPGRADE_DELAY: u64 = 86_400;

/// topics: ("upgrade_proposed", wasm_hash)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UpgradeProposed {
    #[topic]
    pub wasm_hash: BytesN<32>,
    pub proposed_at: u64,
    pub ready_at: u64,
}

/// topics: ("upgrade_executed", wasm_hash)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UpgradeExecuted {
    #[topic]
    pub wasm_hash: BytesN<32>,
    pub executed_at: u64,
}

/// topics: ("upgrade_cancelled", wasm_hash)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UpgradeCancelled {
    #[topic]
    pub wasm_hash: BytesN<32>,
    pub cancelled_at: u64,
}

/// topics: ("upgradeability_renounced",)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UpgradeabilityRenounced {
    pub renounced_at: u64,
    pub admin: Address,
}

/// The probe has no instance-TTL policy of its own; it is never deployed for
/// real. Kept as a no-op so the body below stays identical to the registry's.
fn bump_instance(_env: &Env) {}

/// Load the admin and require its authorization, after refusing outright if
/// upgradeability has been renounced.
///
/// The renounce check comes FIRST on purpose: after renouncing there is no
/// privileged upgrade caller at all, so answering "not authorized" to the admin
/// would be the wrong story. The contract is not guarding a door; the door is
/// gone.
fn require_upgrade_admin(env: &Env) -> Result<Address, ProbeError> {
    if UpgradeProbe::is_upgrade_renounced(env) {
        return Err(ProbeError::UpgradeabilityRenounced);
    }
    let admin = UpgradeProbe::get_admin(env.clone())?;
    admin.require_auth();
    Ok(admin)
}

#[contractimpl]
impl UpgradeProbe {
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
    pub fn propose_upgrade(env: Env, wasm_hash: BytesN<32>) -> Result<u64, ProbeError> {
        require_upgrade_admin(&env)?;

        if env.storage().instance().has(&DataKey::PendingUpgrade) {
            return Err(ProbeError::UpgradeAlreadyPending);
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
    pub fn execute_upgrade(env: Env) -> Result<(), ProbeError> {
        require_upgrade_admin(&env)?;

        let pending: PendingUpgrade = env
            .storage()
            .instance()
            .get(&DataKey::PendingUpgrade)
            .ok_or(ProbeError::NoPendingUpgrade)?;

        let now = env.ledger().timestamp();
        if now < pending.ready_at {
            return Err(ProbeError::UpgradeNotReady);
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
    pub fn cancel_upgrade(env: Env) -> Result<(), ProbeError> {
        require_upgrade_admin(&env)?;

        let pending: PendingUpgrade = env
            .storage()
            .instance()
            .get(&DataKey::PendingUpgrade)
            .ok_or(ProbeError::NoPendingUpgrade)?;

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
    pub fn renounce_upgradeability(env: Env) -> Result<(), ProbeError> {
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

impl UpgradeProbe {
    /// Internal read of the one-way renounce flag. Not an entrypoint: the public
    /// surface is `is_upgradeable`, phrased the way a caller thinks about it.
    fn is_upgrade_renounced(env: &Env) -> bool {
        env.storage()
            .instance()
            .get(&DataKey::UpgradeRenounced)
            .unwrap_or(false)
    }
}
