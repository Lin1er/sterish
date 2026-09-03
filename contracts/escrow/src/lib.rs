#![no_std]

mod data;
mod test;

pub use data::{
    AuditRequest, AuditStatus, BondPosted, EscrowError, RequestCreated, Settled, Slashed,
    StorageKey,
};
use data::{BUMP_THRESHOLD, BUMP_TO};
use soroban_sdk::{contract, contractimpl, token::TokenClient, Address, Env, String};

#[contract]
pub struct UsdcEscrow;

/// Bump the instance entry (token/admin/counter) on every write.
fn bump_instance(env: &Env) {
    env.storage().instance().extend_ttl(BUMP_THRESHOLD, BUMP_TO);
}

/// Bump one persistent job entry. `extend_ttl` is a floor-only no-op when the
/// current TTL already exceeds the threshold, so calling it on every write is
/// safe and cheap. The scaffold never extended `Request(id)` at all, so a job
/// could be archived out from under its escrowed funds.
fn bump_request(env: &Env, request_id: u32) {
    env.storage().persistent().extend_ttl(
        &StorageKey::Request(request_id),
        BUMP_THRESHOLD,
        BUMP_TO,
    );
}

/// Assert a job is in exactly `want`, mapping every other state to the error the
/// caller actually needs to see (`AlreadySettled` / `AlreadySlashed` are far more
/// actionable than a generic "wrong state").
fn require_status(request: &AuditRequest, want: AuditStatus) -> Result<(), EscrowError> {
    if request.status == want {
        return Ok(());
    }
    Err(match request.status {
        AuditStatus::Settled => EscrowError::AlreadySettled,
        AuditStatus::Slashed => EscrowError::AlreadySlashed,
        AuditStatus::Open => EscrowError::NotBonded,
        AuditStatus::Bonded => EscrowError::NotOpen,
    })
}

#[contractimpl]
impl UsdcEscrow {
    /// Shared body of `slash` / `claim_forfeited`. Caller MUST have already
    /// checked admin auth. Moves the bond to `reporter`, refunds the fee to the
    /// requestor, and makes the transition terminal so it can never run twice.
    fn slash_to(env: &Env, request_id: u32, reporter: Address) -> Result<(), EscrowError> {
        let mut request = Self::get_request(env.clone(), request_id)?;
        require_status(&request, AuditStatus::Bonded)?;

        let usdc = Self::get_usdc_token(env.clone())?;
        let token = TokenClient::new(env, &usdc);
        let contract_id = env.current_contract_address();
        let bond = request.bond_amount;

        // Bond to whoever reported the bad audit; fee back to who paid it.
        token.transfer(&contract_id, &reporter, &bond);
        token.transfer(&contract_id, &request.requestor, &request.fee_amount);

        request.status = AuditStatus::Slashed;
        request.resolved_at = env.ledger().timestamp();
        env.storage()
            .persistent()
            .set(&StorageKey::Request(request_id), &request);

        bump_request(env, request_id);
        bump_instance(env);

        Slashed {
            request_id,
            reporter,
            bond,
        }
        .publish(env);

        Ok(())
    }

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

    /// Open an audit job and escrow the fee in one call.
    ///
    /// The design doc (§4.2) splits this into `open` + `fund_fee`; the ticket
    /// recommends keeping the scaffold's single-step pull for the MVP, so the
    /// fee is transferred here and the job is never `Open` while unfunded.
    ///
    /// `bond_amount` is fixed HERE, by the party paying, and `post_bond` later
    /// transfers exactly this much. In the scaffold the auditor chose their own
    /// bond at `post_bond` time and could post 1 stroop while still collecting
    /// `fee + bond` at settle, which zeroed out the honesty incentive.
    pub fn create_audit_request(
        env: Env,
        requestor: Address,
        skill_id: String,
        version: String,
        fee_amount: i128,
        bond_amount: i128,
    ) -> Result<u32, EscrowError> {
        requestor.require_auth();

        if skill_id.is_empty() || version.is_empty() {
            return Err(EscrowError::InvalidInput);
        }
        // i128 is signed and the SAC reads `transfer(from, to, -n)` as a pull in
        // the opposite direction, so the sign is validated explicitly rather
        // than delegated to the token contract.
        if fee_amount <= 0 || bond_amount <= 0 {
            return Err(EscrowError::InvalidAmount);
        }

        let usdc = Self::get_usdc_token(env.clone())?;
        let contract_id = env.current_contract_address();

        // Reverts the whole call if the requestor cannot cover the fee.
        TokenClient::new(&env, &usdc).transfer(&requestor, &contract_id, &fee_amount);

        let request_id: u32 = env
            .storage()
            .instance()
            .get(&StorageKey::NextRequestId)
            .ok_or(EscrowError::NotInitialized)?;
        env.storage()
            .instance()
            .set(&StorageKey::NextRequestId, &(request_id + 1));

        let request = AuditRequest {
            requestor: requestor.clone(),
            auditor: None,
            skill_id: skill_id.clone(),
            version,
            fee_amount,
            bond_amount,
            status: AuditStatus::Open,
            created_at: env.ledger().timestamp(),
            resolved_at: 0,
        };
        env.storage()
            .persistent()
            .set(&StorageKey::Request(request_id), &request);

        bump_request(&env, request_id);
        bump_instance(&env);

        RequestCreated {
            request_id,
            requestor,
            skill_id,
            fee: fee_amount,
        }
        .publish(&env);

        Ok(request_id)
    }

    /// Auditor locks the bond agreed at create time and takes the job.
    ///
    /// There is deliberately no `amount` parameter: the amount is
    /// `request.bond_amount`, so underpaying is not expressible.
    pub fn post_bond(env: Env, auditor: Address, request_id: u32) -> Result<(), EscrowError> {
        auditor.require_auth();

        let mut request = Self::get_request(env.clone(), request_id)?;
        require_status(&request, AuditStatus::Open)?;

        // A requestor auditing their own job would be both sides of the bond.
        if auditor == request.requestor {
            return Err(EscrowError::SelfAudit);
        }

        let usdc = Self::get_usdc_token(env.clone())?;
        let contract_id = env.current_contract_address();
        let bond = request.bond_amount;

        // Reverts the whole call if the auditor cannot cover the agreed bond.
        TokenClient::new(&env, &usdc).transfer(&auditor, &contract_id, &bond);

        request.auditor = Some(auditor.clone());
        request.status = AuditStatus::Bonded;
        env.storage()
            .persistent()
            .set(&StorageKey::Request(request_id), &request);

        bump_request(&env, request_id);
        bump_instance(&env);

        BondPosted {
            request_id,
            auditor,
            bond,
        }
        .publish(&env);

        Ok(())
    }

    /// Pay the auditor `fee + bond` and close the job as `Settled`.
    ///
    /// ## Gating (MVP testnet)
    /// Admin-gated. The admin key is the same key that holds the auditor role on
    /// the Registry contract. The source of truth for the verdict is the
    /// Registry's `version_recorded` event, read OFF-CHAIN by the operator
    /// before calling this. Nothing on-chain here verifies the verdict.
    ///
    /// Roadmap (outside the SOW scope): a dispute window plus a verdict-gated
    /// path that reads the Registry record on-chain, and TEE attestation of the
    /// pipeline — see the "MVP auth note" in SYSTEM_DESIGN §4.2 and
    /// docs/architecture.md §2.
    pub fn settle(env: Env, request_id: u32) -> Result<(), EscrowError> {
        Self::get_admin(env.clone())?.require_auth();

        let mut request = Self::get_request(env.clone(), request_id)?;
        require_status(&request, AuditStatus::Bonded)?;

        // `Bonded` is only reachable through post_bond, which always sets Some.
        let auditor = request.auditor.clone().ok_or(EscrowError::NotBonded)?;

        // Both operands are > 0 (validated at create), so this can only trip on
        // absurd inputs; reported as InvalidAmount rather than trapping.
        let payout = request
            .fee_amount
            .checked_add(request.bond_amount)
            .ok_or(EscrowError::InvalidAmount)?;

        let usdc = Self::get_usdc_token(env.clone())?;
        // The contract is `from`, so it authorizes itself implicitly — no extra
        // require_auth is needed or wanted here.
        TokenClient::new(&env, &usdc).transfer(&env.current_contract_address(), &auditor, &payout);

        request.status = AuditStatus::Settled;
        request.resolved_at = env.ledger().timestamp();
        env.storage()
            .persistent()
            .set(&StorageKey::Request(request_id), &request);

        bump_request(&env, request_id);
        bump_instance(&env);

        Settled { request_id, payout }.publish(&env);

        Ok(())
    }

    /// Forfeit the auditor's bond to `reporter` and refund the fee to the
    /// requestor, closing the job as `Slashed`.
    ///
    /// The scaffold left the bond sitting in the contract, so whoever caught the
    /// bad audit was never paid and the funds needed a second admin call to move.
    ///
    /// ## Gating (MVP testnet)
    /// Admin-gated, with the same off-chain verdict source and the same roadmap
    /// as [`UsdcEscrow::settle`].
    pub fn slash(env: Env, request_id: u32, reporter: Address) -> Result<(), EscrowError> {
        Self::get_admin(env.clone())?.require_auth();
        Self::slash_to(&env, request_id, reporter)
    }

    /// Slash with the admin as the reporter — the documented fallback for when
    /// the bad audit was caught internally and there is no external reporter to
    /// pay. Exactly equivalent to `slash(request_id, admin)`.
    ///
    /// ## Why this is not the scaffold's function any more
    /// The scaffold ran this AFTER `slash`, required status `Slashed`, and
    /// changed no state. Since `Slashed` is terminal, the admin could call it
    /// repeatedly and each call drained another `bond_amount` from the shared
    /// contract balance — i.e. out of OTHER jobs' escrowed funds. It now
    /// requires `Bonded` and performs the terminal transition itself, so a
    /// second call always fails with `AlreadySlashed`.
    pub fn claim_forfeited(env: Env, request_id: u32) -> Result<(), EscrowError> {
        let admin = Self::get_admin(env.clone())?;
        admin.require_auth();
        Self::slash_to(&env, request_id, admin)
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
