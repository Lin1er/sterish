#![cfg(test)]

use crate::{AuditStatus, UsdcEscrow, UsdcEscrowClient};
use soroban_sdk::{
    testutils::Address as _,
    token::{Client as TokenClient, StellarAssetClient},
    Address, Env,
};

fn create_usdc_token(env: &Env) -> Address {
    let admin = Address::generate(env);
    env.register_stellar_asset_contract_v2(admin.clone()).address()
}

fn create_test_env() -> (Env, Address, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let requestor = Address::generate(&env);
    let auditor = Address::generate(&env);
    (env, admin, requestor, auditor)
}

fn register_and_init<'a>(
    env: &'a Env,
    admin: &Address,
    usdc: &Address,
) -> (Address, UsdcEscrowClient<'a>) {
    let contract_id = env.register_contract(None, UsdcEscrow);
    let client = UsdcEscrowClient::new(env, &contract_id);
    client.initialize(usdc, admin);
    (contract_id, client)
}

fn mint(env: &Env, usdc: &Address, to: &Address, amount: i128) {
    let sa = StellarAssetClient::new(env, usdc);
    sa.mint(to, &amount);
}

#[test]
fn test_initialize() {
    let (env, admin, _requestor, _auditor) = create_test_env();
    let usdc = create_usdc_token(&env);
    let (_, _client) = register_and_init(&env, &admin, &usdc);
    // Init succeeded — verified by no panic above.
}

#[test]
#[should_panic(expected = "already initialized")]
fn test_double_initialize_panics() {
    let (env, admin, _requestor, _auditor) = create_test_env();
    let usdc = create_usdc_token(&env);
    let (_, client) = register_and_init(&env, &admin, &usdc);
    client.initialize(&usdc, &admin);
}

#[test]
fn test_create_and_get_request() {
    let (env, admin, requestor, _auditor) = create_test_env();
    let usdc = create_usdc_token(&env);
    let (_, client) = register_and_init(&env, &admin, &usdc);

    mint(&env, &usdc, &requestor, 10_000_000);

    let req_id = client.create_audit_request(&requestor, &5_000_000);
    assert_eq!(req_id, 1);

    let req = client.get_request(&req_id);
    assert_eq!(req.requestor, requestor);
    assert_eq!(req.fee_amount, 5_000_000);
    assert_eq!(req.status, AuditStatus::Open as u32);
}

#[test]
fn test_post_bond() {
    let (env, admin, requestor, auditor) = create_test_env();
    let usdc = create_usdc_token(&env);
    let (_, client) = register_and_init(&env, &admin, &usdc);

    mint(&env, &usdc, &requestor, 10_000_000);
    mint(&env, &usdc, &auditor, 10_000_000);

    let req_id = client.create_audit_request(&requestor, &5_000_000);
    client.post_bond(&auditor, &req_id, &3_000_000);

    let req = client.get_request(&req_id);
    assert_eq!(req.auditor, auditor);
    assert_eq!(req.bond_amount, 3_000_000);
    assert_eq!(req.status, AuditStatus::Bonded as u32);
}

#[test]
fn test_settle() {
    let (env, admin, requestor, auditor) = create_test_env();
    let usdc = create_usdc_token(&env);
    let (contract_id, client) = register_and_init(&env, &admin, &usdc);

    mint(&env, &usdc, &requestor, 10_000_000);
    mint(&env, &usdc, &auditor, 10_000_000);

    let req_id = client.create_audit_request(&requestor, &5_000_000);
    client.post_bond(&auditor, &req_id, &3_000_000);

    let auditor_balance_before = TokenClient::new(&env, &usdc).balance(&auditor);
    client.settle(&req_id);
    let auditor_balance_after = TokenClient::new(&env, &usdc).balance(&auditor);

    // Auditor gets fee (5M) + bond (3M) back = 8M total payout.
    assert_eq!(auditor_balance_after - auditor_balance_before, 8_000_000);

    let req = client.get_request(&req_id);
    assert_eq!(req.status, AuditStatus::Settled as u32);
}

#[test]
fn test_slash() {
    let (env, admin, requestor, auditor) = create_test_env();
    let usdc = create_usdc_token(&env);
    let (contract_id, client) = register_and_init(&env, &admin, &usdc);

    mint(&env, &usdc, &requestor, 10_000_000);
    mint(&env, &usdc, &auditor, 10_000_000);

    let req_id = client.create_audit_request(&requestor, &5_000_000);
    client.post_bond(&auditor, &req_id, &3_000_000);

    let requestor_balance_before = TokenClient::new(&env, &usdc).balance(&requestor);
    client.slash(&req_id);
    let requestor_balance_after = TokenClient::new(&env, &usdc).balance(&requestor);

    // Requestor gets fee back (5M).
    assert_eq!(
        requestor_balance_after - requestor_balance_before,
        5_000_000
    );

    let req = client.get_request(&req_id);
    assert_eq!(req.status, AuditStatus::Slashed as u32);
}

#[test]
fn test_claim_forfeited() {
    let (env, admin, requestor, auditor) = create_test_env();
    let usdc = create_usdc_token(&env);
    let (contract_id, client) = register_and_init(&env, &admin, &usdc);

    mint(&env, &usdc, &requestor, 10_000_000);
    mint(&env, &usdc, &auditor, 10_000_000);

    let req_id = client.create_audit_request(&requestor, &5_000_000);
    client.post_bond(&auditor, &req_id, &3_000_000);
    client.slash(&req_id);

    let admin_balance_before = TokenClient::new(&env, &usdc).balance(&admin);
    client.claim_forfeited(&req_id);
    let admin_balance_after = TokenClient::new(&env, &usdc).balance(&admin);

    // Admin claims the forfeited bond (3M).
    assert_eq!(admin_balance_after - admin_balance_before, 3_000_000);
}

#[test]
#[should_panic(expected = "request not found")]
fn test_get_nonexistent_request() {
    let (env, admin, _requestor, _auditor) = create_test_env();
    let usdc = create_usdc_token(&env);
    let (_, client) = register_and_init(&env, &admin, &usdc);
    client.get_request(&999);
}

#[test]
#[should_panic(expected = "request not open")]
fn test_bond_non_open_request() {
    let (env, admin, requestor, auditor) = create_test_env();
    let usdc = create_usdc_token(&env);
    let (_, client) = register_and_init(&env, &admin, &usdc);

    mint(&env, &usdc, &requestor, 10_000_000);
    mint(&env, &usdc, &auditor, 10_000_000);

    let req_id = client.create_audit_request(&requestor, &5_000_000);
    client.post_bond(&auditor, &req_id, &3_000_000);
    // Double bond should panic.
    client.post_bond(&auditor, &req_id, &1_000_000);
}
