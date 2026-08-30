#![no_std]

mod test;

use soroban_sdk::{
    contract, contractimpl, contracttype, symbol_short, Address, Env, String, U256,
};

/// Status of an audit escrow request.
#[derive(Clone, Debug, Eq, PartialEq)]
#[contracttype]
#[repr(u32)]
pub enum AuditStatus {
    Open = 0,
    Bonded = 1,
    Settled = 2,
    Slashed = 3,
}

/// An audit escrow request.
#[derive(Clone, Debug, Eq, PartialEq)]
#[contracttype]
pub struct AuditRequest {
    pub requestor: Address,
    pub auditor: Address,
    pub fee_amount: i128,
    pub bond_amount: i128,
    pub status: u32,
    pub created_at: u64,
}

/// Storage keys.
#[derive(Clone, Debug)]
#[contracttype]
pub enum StorageKey {
    Request(u32),
    UsdcToken,
    Admin,
    RequestCount,
    NextRequestId,
}

#[contract]
pub struct UsdcEscrow;

#[contractimpl]
impl UsdcEscrow {
    /// Initialize the contract with the USDC token address and admin.
    pub fn initialize(env: Env, usdc_token: Address, admin: Address) {
        if env.storage().instance().has(&StorageKey::Admin) {
            panic!("already initialized");
        }
        admin.require_auth();
        env.storage().instance().set(&StorageKey::UsdcToken, &usdc_token);
        env.storage().instance().set(&StorageKey::Admin, &admin);
        env.storage().instance().set(&StorageKey::RequestCount, &0u32);
        env.storage().instance().set(&StorageKey::NextRequestId, &1u32);
    }

    /// Create a new audit request. The requestor must transfer `fee_amount` USDC to this contract.
    pub fn create_audit_request(env: Env, requestor: Address, fee_amount: i128) -> u32 {
        requestor.require_auth();

        let usdc_token: Address = env
            .storage()
            .instance()
            .get(&StorageKey::UsdcToken)
            .unwrap_or_else(|| panic!("not initialized"));

        let contract_id = env.current_contract_address();

        // Transfer fee from requestor to this contract.
        soroban_sdk::token::Client::new(&env, &usdc_token).transfer(
            &requestor,
            &contract_id,
            &fee_amount,
        );

        let mut count: u32 = env
            .storage()
            .instance()
            .get(&StorageKey::RequestCount)
            .unwrap_or(0u32);
        count += 1;
        env.storage().instance().set(&StorageKey::RequestCount, &count);

        let request_id: u32 = env
            .storage()
            .instance()
            .get(&StorageKey::NextRequestId)
            .unwrap_or(1u32);
        env.storage()
            .instance()
            .set(&StorageKey::NextRequestId, &(request_id + 1));

        let request = AuditRequest {
            requestor: requestor.clone(),
            auditor: requestor.clone(), // placeholder until bonded
            fee_amount,
            bond_amount: 0,
            status: AuditStatus::Open as u32,
            created_at: env.ledger().timestamp(),
        };
        env.storage()
            .persistent()
            .set(&StorageKey::Request(request_id), &request);

        request_id
    }

    /// Auditor posts a bond for an open audit request.
    pub fn post_bond(env: Env, auditor: Address, request_id: u32, amount: i128) {
        auditor.require_auth();

        let mut request: AuditRequest = env
            .storage()
            .persistent()
            .get(&StorageKey::Request(request_id))
            .unwrap_or_else(|| panic!("request not found"));

        if request.status != AuditStatus::Open as u32 {
            panic!("request not open");
        }

        let usdc_token: Address = env
            .storage()
            .instance()
            .get(&StorageKey::UsdcToken)
            .unwrap_or_else(|| panic!("not initialized"));

        let contract_id = env.current_contract_address();
        soroban_sdk::token::Client::new(&env, &usdc_token).transfer(
            &auditor,
            &contract_id,
            &amount,
        );

        request.auditor = auditor;
        request.bond_amount = amount;
        request.status = AuditStatus::Bonded as u32;
        env.storage()
            .persistent()
            .set(&StorageKey::Request(request_id), &request);
    }

    /// Settle an audit: auditor passed, pay fee to auditor, return bond.
    pub fn settle(env: Env, request_id: u32) {
        let admin: Address = env
            .storage()
            .instance()
            .get(&StorageKey::Admin)
            .unwrap_or_else(|| panic!("not initialized"));
        admin.require_auth();

        let mut request: AuditRequest = env
            .storage()
            .persistent()
            .get(&StorageKey::Request(request_id))
            .unwrap_or_else(|| panic!("request not found"));

        if request.status != AuditStatus::Bonded as u32 {
            panic!("request not bonded");
        }

        let usdc_token: Address = env
            .storage()
            .instance()
            .get(&StorageKey::UsdcToken)
            .unwrap_or_else(|| panic!("not initialized"));

        let contract_id = env.current_contract_address();

        // Pay auditor: fee + bond return.
        let payout = request.fee_amount + request.bond_amount;
        soroban_sdk::token::Client::new(&env, &usdc_token).transfer(
            &contract_id,
            &request.auditor,
            &payout,
        );

        request.status = AuditStatus::Settled as u32;
        env.storage()
            .persistent()
            .set(&StorageKey::Request(request_id), &request);
    }

    /// Slash an audit: auditor failed, bond forfeited (stays), fee refunded.
    pub fn slash(env: Env, request_id: u32) {
        let admin: Address = env
            .storage()
            .instance()
            .get(&StorageKey::Admin)
            .unwrap_or_else(|| panic!("not initialized"));
        admin.require_auth();

        let mut request: AuditRequest = env
            .storage()
            .persistent()
            .get(&StorageKey::Request(request_id))
            .unwrap_or_else(|| panic!("request not found"));

        if request.status != AuditStatus::Bonded as u32 {
            panic!("request not bonded");
        }

        let usdc_token: Address = env
            .storage()
            .instance()
            .get(&StorageKey::UsdcToken)
            .unwrap_or_else(|| panic!("not initialized"));

        let contract_id = env.current_contract_address();

        // Refund fee to requestor.
        soroban_sdk::token::Client::new(&env, &usdc_token).transfer(
            &contract_id,
            &request.requestor,
            &request.fee_amount,
        );

        // Bond is forfeited — stays in contract (can be claimed by admin later).

        request.status = AuditStatus::Slashed as u32;
        env.storage()
            .persistent()
            .set(&StorageKey::Request(request_id), &request);
    }

    /// Get an audit request by ID.
    pub fn get_request(env: Env, request_id: u32) -> AuditRequest {
        env.storage()
            .persistent()
            .get(&StorageKey::Request(request_id))
            .unwrap_or_else(|| panic!("request not found"))
    }

    /// Admin claims forfeited bond (slash residue).
    pub fn claim_forfeited(env: Env, request_id: u32) {
        let admin: Address = env
            .storage()
            .instance()
            .get(&StorageKey::Admin)
            .unwrap_or_else(|| panic!("not initialized"));
        admin.require_auth();

        let request: AuditRequest = env
            .storage()
            .persistent()
            .get(&StorageKey::Request(request_id))
            .unwrap_or_else(|| panic!("request not found"));

        if request.status != AuditStatus::Slashed as u32 {
            panic!("request not slashed");
        }

        let usdc_token: Address = env
            .storage()
            .instance()
            .get(&StorageKey::UsdcToken)
            .unwrap_or_else(|| panic!("not initialized"));

        let contract_id = env.current_contract_address();
        soroban_sdk::token::Client::new(&env, &usdc_token).transfer(
            &contract_id,
            &admin,
            &request.bond_amount,
        );
    }
}
