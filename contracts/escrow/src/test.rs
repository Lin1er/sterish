#![cfg(test)]
extern crate std;

use crate::{
    data::{BUMP_THRESHOLD, BUMP_TO, DAY_IN_LEDGERS},
    AuditStatus, BondPosted, EscrowError, RequestCreated, Settled, Slashed, StorageKey, UsdcEscrow,
    UsdcEscrowClient,
};
use soroban_sdk::{
    testutils::{
        storage::{Instance as _, Persistent as _},
        Address as _, Events as _, Ledger, MockAuth, MockAuthInvoke,
    },
    token::{StellarAssetClient, TokenClient},
    Address, Env, Event, IntoVal, String,
};

const FEE: i128 = 5_000_000;
const BOND: i128 = 3_000_000;
const MINT: i128 = 10_000_000;

/// Assert that a `try_*` call returned our typed contract error.
macro_rules! assert_escrow_err {
    ($res:expr, $want:expr) => {
        match $res {
            Err(Ok(e)) => assert_eq!(e, $want),
            other => std::panic!("expected {:?}, got {:?}", $want, other),
        }
    };
}

struct Ctx {
    env: Env,
    contract_id: Address,
    usdc: Address,
    admin: Address,
    requestor: Address,
    auditor: Address,
    reporter: Address,
}

impl Ctx {
    fn client(&self) -> UsdcEscrowClient<'_> {
        UsdcEscrowClient::new(&self.env, &self.contract_id)
    }

    fn token(&self) -> TokenClient<'_> {
        TokenClient::new(&self.env, &self.usdc)
    }

    fn bal(&self, who: &Address) -> i128 {
        self.token().balance(who)
    }

    /// Balance of the escrow contract itself — the invariant every money test
    /// checks, because all jobs share one pot.
    fn escrowed(&self) -> i128 {
        self.bal(&self.contract_id)
    }

    fn s(&self, text: &str) -> String {
        String::from_str(&self.env, text)
    }

    fn skill(&self) -> String {
        self.s("com.example.send-email")
    }

    fn version(&self) -> String {
        self.s("1.0.0")
    }

    /// Mint fresh USDC to a brand new address.
    fn funded(&self, amount: i128) -> Address {
        let who = Address::generate(&self.env);
        StellarAssetClient::new(&self.env, &self.usdc).mint(&who, &amount);
        who
    }

    /// Open a job and have `auditor` bond it. Returns the request id.
    fn bonded_job(&self) -> u32 {
        let client = self.client();
        let id = client.create_audit_request(
            &self.requestor,
            &self.skill(),
            &self.version(),
            &FEE,
            &BOND,
        );
        client.post_bond(&self.auditor, &id);
        id
    }
}

/// Deploy with all auths mocked and both parties funded — used by every test
/// that is not about auth itself.
fn setup() -> Ctx {
    let env = Env::default();
    env.mock_all_auths();

    let issuer = Address::generate(&env);
    let usdc = env.register_stellar_asset_contract_v2(issuer).address();

    let admin = Address::generate(&env);
    let requestor = Address::generate(&env);
    let auditor = Address::generate(&env);
    let reporter = Address::generate(&env);

    let contract_id = env.register(UsdcEscrow, (usdc.clone(), admin.clone()));

    let sac = StellarAssetClient::new(&env, &usdc);
    sac.mint(&requestor, &MINT);
    sac.mint(&auditor, &MINT);

    Ctx {
        env,
        contract_id,
        usdc,
        admin,
        requestor,
        auditor,
        reporter,
    }
}

// ---------------------------------------------------------------------------
// constructor + views
// ---------------------------------------------------------------------------

#[test]
fn test_constructor_sets_state() {
    let ctx = setup();
    let client = ctx.client();

    assert_eq!(client.get_admin(), ctx.admin);
    assert_eq!(client.get_usdc_token(), ctx.usdc);
    assert_eq!(client.get_request_count(), 0);
    assert_eq!(ctx.escrowed(), 0);
    assert_escrow_err!(client.try_get_request(&1), EscrowError::RequestNotFound);
}

#[test]
fn test_get_request_not_found() {
    let ctx = setup();
    assert_escrow_err!(
        ctx.client().try_get_request(&999),
        EscrowError::RequestNotFound
    );
}

#[test]
fn test_request_count_tracks_created_jobs() {
    let ctx = setup();
    let client = ctx.client();
    assert_eq!(client.get_request_count(), 0);

    let id1 =
        client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);
    assert_eq!(id1, 1);
    assert_eq!(client.get_request_count(), 1);

    let id2 =
        client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.s("2.0.0"), &FEE, &BOND);
    assert_eq!(id2, 2);
    assert_eq!(client.get_request_count(), 2);
}

// ---------------------------------------------------------------------------
// create_audit_request
// ---------------------------------------------------------------------------

#[test]
fn test_create_audit_request_pulls_fee() {
    let ctx = setup();
    let client = ctx.client();

    let requestor_before = ctx.bal(&ctx.requestor);
    assert_eq!(ctx.escrowed(), 0);

    ctx.env.ledger().set_timestamp(1_700_000_000);
    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    assert_eq!(ctx.bal(&ctx.requestor), requestor_before - FEE);
    assert_eq!(ctx.escrowed(), FEE);
    // Nobody else was touched.
    assert_eq!(ctx.bal(&ctx.auditor), MINT);
    assert_eq!(ctx.bal(&ctx.admin), 0);

    let req = client.get_request(&id);
    assert_eq!(req.requestor, ctx.requestor);
    assert_eq!(req.auditor, None);
    assert_eq!(req.skill_id, ctx.skill());
    assert_eq!(req.version, ctx.version());
    assert_eq!(req.fee_amount, FEE);
    assert_eq!(req.bond_amount, BOND);
    assert_eq!(req.status, AuditStatus::Open);
    assert_eq!(req.created_at, 1_700_000_000);
    assert_eq!(req.resolved_at, 0);
}

#[test]
fn test_create_requires_requestor_auth() {
    let ctx = setup();
    let client = ctx.client();
    let attacker = Address::generate(&ctx.env);

    // Only the attacker signed, but the call claims to be the requestor.
    let res = client
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "create_audit_request",
                args: (attacker.clone(), ctx.skill(), ctx.version(), FEE, BOND).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    assert!(res.is_err(), "create must reject a missing requestor auth");
    assert_eq!(ctx.bal(&ctx.requestor), MINT, "no fee may be pulled");
    assert_eq!(ctx.escrowed(), 0);
    assert_eq!(client.get_request_count(), 0);
}

#[test]
fn test_create_with_exact_auth_tree_succeeds() {
    let ctx = setup();
    let client = ctx.client();

    // The requestor authorizes the escrow call AND the token transfer it makes.
    let id = client
        .mock_auths(&[MockAuth {
            address: &ctx.requestor,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "create_audit_request",
                args: (ctx.requestor.clone(), ctx.skill(), ctx.version(), FEE, BOND)
                    .into_val(&ctx.env),
                sub_invokes: &[MockAuthInvoke {
                    contract: &ctx.usdc,
                    fn_name: "transfer",
                    args: (ctx.requestor.clone(), ctx.contract_id.clone(), FEE).into_val(&ctx.env),
                    sub_invokes: &[],
                }],
            },
        }])
        .create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    assert_eq!(id, 1);
    assert_eq!(ctx.escrowed(), FEE);
}

#[test]
fn test_create_zero_fee_rejected() {
    let ctx = setup();
    assert_escrow_err!(
        ctx.client().try_create_audit_request(
            &ctx.requestor,
            &ctx.skill(),
            &ctx.version(),
            &0,
            &BOND
        ),
        EscrowError::InvalidAmount
    );
    assert_eq!(ctx.escrowed(), 0);
}

#[test]
fn test_create_negative_fee_rejected() {
    let ctx = setup();
    // transfer(from, to, -n) is a reverse pull at the SAC level, so a negative
    // fee must never reach the token contract.
    assert_escrow_err!(
        ctx.client().try_create_audit_request(
            &ctx.requestor,
            &ctx.skill(),
            &ctx.version(),
            &-FEE,
            &BOND
        ),
        EscrowError::InvalidAmount
    );
    assert_eq!(ctx.bal(&ctx.requestor), MINT);
    assert_eq!(ctx.escrowed(), 0);
}

#[test]
fn test_create_zero_bond_rejected() {
    let ctx = setup();
    assert_escrow_err!(
        ctx.client().try_create_audit_request(
            &ctx.requestor,
            &ctx.skill(),
            &ctx.version(),
            &FEE,
            &0
        ),
        EscrowError::InvalidAmount
    );
}

#[test]
fn test_create_negative_bond_rejected() {
    let ctx = setup();
    assert_escrow_err!(
        ctx.client().try_create_audit_request(
            &ctx.requestor,
            &ctx.skill(),
            &ctx.version(),
            &FEE,
            &-BOND
        ),
        EscrowError::InvalidAmount
    );
    assert_eq!(ctx.escrowed(), 0);
}

#[test]
fn test_create_empty_skill_id_rejected() {
    let ctx = setup();
    assert_escrow_err!(
        ctx.client().try_create_audit_request(
            &ctx.requestor,
            &ctx.s(""),
            &ctx.version(),
            &FEE,
            &BOND
        ),
        EscrowError::InvalidInput
    );
    assert_eq!(ctx.escrowed(), 0);
}

#[test]
fn test_create_empty_version_rejected() {
    let ctx = setup();
    assert_escrow_err!(
        ctx.client().try_create_audit_request(
            &ctx.requestor,
            &ctx.skill(),
            &ctx.s(""),
            &FEE,
            &BOND
        ),
        EscrowError::InvalidInput
    );
    assert_eq!(ctx.escrowed(), 0);
}

#[test]
fn test_create_without_usdc_balance_reverts() {
    let ctx = setup();
    let client = ctx.client();
    let broke = Address::generate(&ctx.env);
    assert_eq!(ctx.bal(&broke), 0);

    let res = client.try_create_audit_request(&broke, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    assert!(
        res.is_err(),
        "create must revert without a funded requestor"
    );
    assert_eq!(ctx.escrowed(), 0, "nothing may be escrowed");
    assert_eq!(client.get_request_count(), 0, "no job may be recorded");
}

#[test]
fn test_create_with_partial_usdc_balance_reverts() {
    let ctx = setup();
    let client = ctx.client();
    let poor = ctx.funded(FEE - 1);

    let res = client.try_create_audit_request(&poor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    assert!(
        res.is_err(),
        "create must revert when the fee is not covered"
    );
    assert_eq!(ctx.bal(&poor), FEE - 1);
    assert_eq!(ctx.escrowed(), 0);
}

// ---------------------------------------------------------------------------
// post_bond
// ---------------------------------------------------------------------------

#[test]
fn test_post_bond_transfers_agreed_amount() {
    let ctx = setup();
    let client = ctx.client();
    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    let auditor_before = ctx.bal(&ctx.auditor);
    client.post_bond(&ctx.auditor, &id);

    // Exactly bond_amount, no more and no less.
    assert_eq!(ctx.bal(&ctx.auditor), auditor_before - BOND);
    assert_eq!(ctx.escrowed(), FEE + BOND);
    assert_eq!(ctx.bal(&ctx.requestor), MINT - FEE);

    let req = client.get_request(&id);
    assert_eq!(req.auditor, Some(ctx.auditor.clone()));
    assert_eq!(req.bond_amount, BOND);
    assert_eq!(req.status, AuditStatus::Bonded);
    assert_eq!(req.resolved_at, 0);
}

/// Bug #8: the scaffold let the auditor pick the bond amount at `post_bond`, so
/// they could lock 1 stroop and still collect `fee + bond` at settle. The amount
/// parameter is gone; the only thing that can be transferred is the amount the
/// requestor agreed to, and an auditor who cannot cover it is rejected outright.
#[test]
fn test_post_bond_cannot_underpay() {
    let ctx = setup();
    let client = ctx.client();
    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    let cheapskate = ctx.funded(BOND - 1);
    let res = client.try_post_bond(&cheapskate, &id);

    assert!(res.is_err(), "an underfunded auditor must not take the job");
    assert_eq!(
        ctx.bal(&cheapskate),
        BOND - 1,
        "no partial bond may be taken"
    );
    assert_eq!(ctx.escrowed(), FEE, "only the fee stays escrowed");
    assert_eq!(client.get_request(&id).status, AuditStatus::Open);
    assert_eq!(client.get_request(&id).auditor, None);

    // The honest path still moves exactly the agreed bond.
    client.post_bond(&ctx.auditor, &id);
    assert_eq!(ctx.escrowed(), FEE + BOND);
    assert_eq!(client.get_request(&id).bond_amount, BOND);
}

#[test]
fn test_post_bond_requires_auditor_auth() {
    let ctx = setup();
    let client = ctx.client();
    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);
    let attacker = Address::generate(&ctx.env);

    let res = client
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "post_bond",
                args: (attacker.clone(), id).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_post_bond(&ctx.auditor, &id);

    assert!(res.is_err(), "post_bond must reject a missing auditor auth");
    assert_eq!(ctx.bal(&ctx.auditor), MINT, "no bond may be pulled");
    assert_eq!(ctx.escrowed(), FEE);
    assert_eq!(client.get_request(&id).status, AuditStatus::Open);
}

#[test]
fn test_post_bond_twice_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    let second = ctx.funded(MINT);

    assert_escrow_err!(client.try_post_bond(&second, &id), EscrowError::NotOpen);
    assert_eq!(
        ctx.bal(&second),
        MINT,
        "the second auditor keeps their money"
    );
    assert_eq!(ctx.escrowed(), FEE + BOND);
    assert_eq!(client.get_request(&id).auditor, Some(ctx.auditor.clone()));
}

#[test]
fn test_post_bond_unknown_request() {
    let ctx = setup();
    assert_escrow_err!(
        ctx.client().try_post_bond(&ctx.auditor, &42),
        EscrowError::RequestNotFound
    );
    assert_eq!(ctx.bal(&ctx.auditor), MINT);
}

#[test]
fn test_post_bond_self_audit_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    assert_escrow_err!(
        client.try_post_bond(&ctx.requestor, &id),
        EscrowError::SelfAudit
    );
    assert_eq!(ctx.escrowed(), FEE, "no self-bond may be escrowed");
    assert_eq!(client.get_request(&id).status, AuditStatus::Open);
}

#[test]
fn test_post_bond_after_settle_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    client.settle(&id);

    let late = ctx.funded(MINT);
    assert_escrow_err!(
        client.try_post_bond(&late, &id),
        EscrowError::AlreadySettled
    );
    assert_eq!(ctx.bal(&late), MINT);
}

#[test]
fn test_post_bond_after_slash_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    client.slash(&id, &ctx.reporter);

    let late = ctx.funded(MINT);
    assert_escrow_err!(
        client.try_post_bond(&late, &id),
        EscrowError::AlreadySlashed
    );
    assert_eq!(ctx.bal(&late), MINT);
}

// ---------------------------------------------------------------------------
// settle
// ---------------------------------------------------------------------------

#[test]
fn test_full_settle_path() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();

    assert_eq!(ctx.bal(&ctx.requestor), MINT - FEE);
    assert_eq!(ctx.bal(&ctx.auditor), MINT - BOND);
    assert_eq!(ctx.escrowed(), FEE + BOND);

    ctx.env.ledger().set_timestamp(1_700_000_500);
    client.settle(&id);

    // Auditor collects the fee plus their own bond back.
    assert_eq!(ctx.bal(&ctx.auditor), MINT + FEE);
    assert_eq!(ctx.bal(&ctx.requestor), MINT - FEE, "fee is not refunded");
    assert_eq!(ctx.bal(&ctx.reporter), 0);
    assert_eq!(ctx.bal(&ctx.admin), 0);
    assert_eq!(ctx.escrowed(), 0, "the escrow pot must be drained exactly");

    let req = client.get_request(&id);
    assert_eq!(req.status, AuditStatus::Settled);
    assert_eq!(req.resolved_at, 1_700_000_500);
    assert!(req.resolved_at > 0);
}

#[test]
fn test_settle_requires_admin_auth() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    let attacker = Address::generate(&ctx.env);

    let res = client
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "settle",
                args: (id,).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_settle(&id);

    assert!(res.is_err(), "settle must reject a non-admin caller");
    assert_eq!(ctx.escrowed(), FEE + BOND, "funds must stay escrowed");
    assert_eq!(ctx.bal(&ctx.auditor), MINT - BOND);
    assert_eq!(client.get_request(&id).status, AuditStatus::Bonded);
}

#[test]
fn test_auditor_cannot_settle_their_own_job() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();

    let res = client
        .mock_auths(&[MockAuth {
            address: &ctx.auditor,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "settle",
                args: (id,).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_settle(&id);

    assert!(res.is_err(), "the auditor must not be able to self-settle");
    assert_eq!(ctx.escrowed(), FEE + BOND);
}

#[test]
fn test_double_settle_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();

    client.settle(&id);
    let after_first = ctx.bal(&ctx.auditor);

    assert_escrow_err!(client.try_settle(&id), EscrowError::AlreadySettled);
    assert_eq!(ctx.bal(&ctx.auditor), after_first, "no second payout");
    assert_eq!(ctx.escrowed(), 0);
}

#[test]
fn test_settle_before_bond_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    assert_escrow_err!(client.try_settle(&id), EscrowError::NotBonded);
    assert_eq!(ctx.escrowed(), FEE);
    assert_eq!(client.get_request(&id).status, AuditStatus::Open);
}

#[test]
fn test_settle_unknown_request() {
    let ctx = setup();
    assert_escrow_err!(ctx.client().try_settle(&7), EscrowError::RequestNotFound);
}

#[test]
fn test_settle_after_slash_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    client.slash(&id, &ctx.reporter);

    assert_escrow_err!(client.try_settle(&id), EscrowError::AlreadySlashed);
    assert_eq!(
        ctx.bal(&ctx.auditor),
        MINT - BOND,
        "the bond stays forfeited"
    );
    assert_eq!(ctx.escrowed(), 0);
}

// ---------------------------------------------------------------------------
// slash
// ---------------------------------------------------------------------------

/// Requirement: the bond must reach the reporter. The scaffold left it in the
/// contract, so whoever caught the bad audit was never paid.
#[test]
fn test_full_slash_path_bond_goes_to_reporter() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();

    assert_eq!(ctx.bal(&ctx.reporter), 0);
    assert_eq!(ctx.escrowed(), FEE + BOND);

    ctx.env.ledger().set_timestamp(1_700_000_900);
    client.slash(&id, &ctx.reporter);

    assert_eq!(
        ctx.bal(&ctx.reporter),
        BOND,
        "the reporter collects the bond"
    );
    assert_eq!(ctx.bal(&ctx.requestor), MINT, "the fee is refunded in full");
    assert_eq!(
        ctx.bal(&ctx.auditor),
        MINT - BOND,
        "the auditor loses the bond"
    );
    assert_eq!(ctx.bal(&ctx.admin), 0, "the admin takes nothing");
    assert_eq!(ctx.escrowed(), 0, "nothing is left stuck in the contract");

    let req = client.get_request(&id);
    assert_eq!(req.status, AuditStatus::Slashed);
    assert_eq!(req.resolved_at, 1_700_000_900);
}

#[test]
fn test_slash_requires_admin_auth() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    let attacker = Address::generate(&ctx.env);

    let res = client
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "slash",
                args: (id, attacker.clone()).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_slash(&id, &attacker);

    assert!(res.is_err(), "slash must reject a non-admin caller");
    assert_eq!(
        ctx.bal(&attacker),
        0,
        "an attacker cannot name themselves reporter"
    );
    assert_eq!(ctx.escrowed(), FEE + BOND);
    assert_eq!(client.get_request(&id).status, AuditStatus::Bonded);
}

#[test]
fn test_double_slash_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();

    client.slash(&id, &ctx.reporter);
    assert_eq!(ctx.bal(&ctx.reporter), BOND);

    assert_escrow_err!(
        client.try_slash(&id, &ctx.reporter),
        EscrowError::AlreadySlashed
    );
    assert_eq!(ctx.bal(&ctx.reporter), BOND, "no second bond payout");
    assert_eq!(ctx.escrowed(), 0);
}

#[test]
fn test_slash_before_bond_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    assert_escrow_err!(client.try_slash(&id, &ctx.reporter), EscrowError::NotBonded);
    assert_eq!(ctx.bal(&ctx.reporter), 0);
    assert_eq!(ctx.escrowed(), FEE);
}

#[test]
fn test_slash_unknown_request() {
    let ctx = setup();
    assert_escrow_err!(
        ctx.client().try_slash(&123, &ctx.reporter),
        EscrowError::RequestNotFound
    );
}

#[test]
fn test_slash_after_settle_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    client.settle(&id);

    assert_escrow_err!(
        client.try_slash(&id, &ctx.reporter),
        EscrowError::AlreadySettled
    );
    assert_eq!(ctx.bal(&ctx.reporter), 0);
    assert_eq!(ctx.escrowed(), 0);
}

// ---------------------------------------------------------------------------
// claim_forfeited (bug #7)
// ---------------------------------------------------------------------------

/// Bug #7: in the scaffold `claim_forfeited` required status `Slashed`, changed
/// no state, and moved `bond_amount` to the admin every time it was called.
/// `Slashed` being terminal meant the admin could call it in a loop and drain
/// OTHER jobs' escrowed USDC out of the shared contract balance.
///
/// Two jobs run in parallel here: the second one's money must be untouched.
#[test]
fn test_claim_forfeited_is_one_shot() {
    let ctx = setup();
    let client = ctx.client();

    // Job A — will be claimed. Job B — an innocent bystander, fully funded.
    let id_a = ctx.bonded_job();
    let requestor_b = ctx.funded(MINT);
    let auditor_b = ctx.funded(MINT);
    let id_b =
        client.create_audit_request(&requestor_b, &ctx.skill(), &ctx.s("2.0.0"), &FEE, &BOND);
    client.post_bond(&auditor_b, &id_b);

    assert_eq!(ctx.escrowed(), 2 * (FEE + BOND));

    client.claim_forfeited(&id_a);

    // Exactly job A's money moved: bond to admin, fee back to its requestor.
    assert_eq!(ctx.bal(&ctx.admin), BOND);
    assert_eq!(ctx.bal(&ctx.requestor), MINT);
    assert_eq!(client.get_request(&id_a).status, AuditStatus::Slashed);

    // A second call cannot happen at all — the transition already ran.
    assert_escrow_err!(
        client.try_claim_forfeited(&id_a),
        EscrowError::AlreadySlashed
    );
    // ...and neither can the equivalent slash.
    assert_escrow_err!(
        client.try_slash(&id_a, &ctx.admin),
        EscrowError::AlreadySlashed
    );

    assert_eq!(ctx.bal(&ctx.admin), BOND, "the admin cannot claim twice");
    assert_eq!(
        ctx.escrowed(),
        FEE + BOND,
        "job B's escrow must be fully intact"
    );

    // Job B still settles normally out of its own funds.
    client.settle(&id_b);
    assert_eq!(ctx.bal(&auditor_b), MINT + FEE);
    assert_eq!(ctx.escrowed(), 0);
}

#[test]
fn test_claim_forfeited_requires_admin_auth() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    let attacker = Address::generate(&ctx.env);

    let res = client
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "claim_forfeited",
                args: (id,).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_claim_forfeited(&id);

    assert!(
        res.is_err(),
        "claim_forfeited must reject a non-admin caller"
    );
    assert_eq!(ctx.bal(&attacker), 0);
    assert_eq!(ctx.escrowed(), FEE + BOND);
    assert_eq!(client.get_request(&id).status, AuditStatus::Bonded);
}

#[test]
fn test_claim_forfeited_before_bond_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    assert_escrow_err!(client.try_claim_forfeited(&id), EscrowError::NotBonded);
    assert_eq!(ctx.bal(&ctx.admin), 0);
    assert_eq!(ctx.escrowed(), FEE);
}

#[test]
fn test_claim_forfeited_after_settle_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    client.settle(&id);

    assert_escrow_err!(client.try_claim_forfeited(&id), EscrowError::AlreadySettled);
    assert_eq!(ctx.bal(&ctx.admin), 0);
}

#[test]
fn test_claim_forfeited_unknown_request() {
    let ctx = setup();
    assert_escrow_err!(
        ctx.client().try_claim_forfeited(&404),
        EscrowError::RequestNotFound
    );
}

// ---------------------------------------------------------------------------
// fund isolation between jobs
// ---------------------------------------------------------------------------

#[test]
fn test_two_parallel_jobs_isolated() {
    let ctx = setup();
    let client = ctx.client();

    // Job A: small, will be settled. Job B: large, will be slashed.
    let big_fee = FEE * 2;
    let big_bond = BOND * 2;
    let requestor_b = ctx.funded(MINT * 2);
    let auditor_b = ctx.funded(MINT * 2);

    let id_a = ctx.bonded_job();
    let id_b = client.create_audit_request(
        &requestor_b,
        &ctx.s("com.example.other"),
        &ctx.version(),
        &big_fee,
        &big_bond,
    );
    client.post_bond(&auditor_b, &id_b);

    assert_eq!(ctx.escrowed(), FEE + BOND + big_fee + big_bond);

    client.settle(&id_a);
    // Job A paid out of job A's money only.
    assert_eq!(ctx.bal(&ctx.auditor), MINT + FEE);
    assert_eq!(ctx.escrowed(), big_fee + big_bond);
    assert_eq!(client.get_request(&id_b).status, AuditStatus::Bonded);

    client.slash(&id_b, &ctx.reporter);
    assert_eq!(ctx.bal(&ctx.reporter), big_bond);
    assert_eq!(ctx.bal(&requestor_b), MINT * 2);
    assert_eq!(ctx.bal(&auditor_b), MINT * 2 - big_bond);
    assert_eq!(ctx.escrowed(), 0);

    // Each job kept its own agreed amounts.
    assert_eq!(client.get_request(&id_a).fee_amount, FEE);
    assert_eq!(client.get_request(&id_b).fee_amount, big_fee);
}

// ---------------------------------------------------------------------------
// events
// ---------------------------------------------------------------------------

#[test]
fn test_request_created_event() {
    let ctx = setup();
    let client = ctx.client();

    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    assert_eq!(
        ctx.env.events().all().filter_by_contract(&ctx.contract_id),
        std::vec![RequestCreated {
            request_id: id,
            requestor: ctx.requestor.clone(),
            skill_id: ctx.skill(),
            fee: FEE,
        }
        .to_xdr(&ctx.env, &ctx.contract_id)]
    );
}

#[test]
fn test_bond_posted_event() {
    let ctx = setup();
    let client = ctx.client();
    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);

    client.post_bond(&ctx.auditor, &id);

    assert_eq!(
        ctx.env.events().all().filter_by_contract(&ctx.contract_id),
        std::vec![BondPosted {
            request_id: id,
            auditor: ctx.auditor.clone(),
            bond: BOND,
        }
        .to_xdr(&ctx.env, &ctx.contract_id)]
    );
}

#[test]
fn test_settled_event() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();

    client.settle(&id);

    assert_eq!(
        ctx.env.events().all().filter_by_contract(&ctx.contract_id),
        std::vec![Settled {
            request_id: id,
            payout: FEE + BOND,
        }
        .to_xdr(&ctx.env, &ctx.contract_id)]
    );
}

#[test]
fn test_slashed_event() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();

    client.slash(&id, &ctx.reporter);

    assert_eq!(
        ctx.env.events().all().filter_by_contract(&ctx.contract_id),
        std::vec![Slashed {
            request_id: id,
            reporter: ctx.reporter.clone(),
            bond: BOND,
        }
        .to_xdr(&ctx.env, &ctx.contract_id)]
    );
}

#[test]
fn test_claim_forfeited_emits_slashed_with_admin_as_reporter() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();

    client.claim_forfeited(&id);

    assert_eq!(
        ctx.env.events().all().filter_by_contract(&ctx.contract_id),
        std::vec![Slashed {
            request_id: id,
            reporter: ctx.admin.clone(),
            bond: BOND,
        }
        .to_xdr(&ctx.env, &ctx.contract_id)]
    );
}

// ---------------------------------------------------------------------------
// TTL
// ---------------------------------------------------------------------------

#[test]
fn test_ttl_extended_on_write() {
    let ctx = setup();
    let client = ctx.client();
    let id = client.create_audit_request(&ctx.requestor, &ctx.skill(), &ctx.version(), &FEE, &BOND);
    let key = StorageKey::Request(id);

    let (request_ttl, instance_ttl) = ctx.env.as_contract(&ctx.contract_id, || {
        (
            ctx.env.storage().persistent().get_ttl(&key),
            ctx.env.storage().instance().get_ttl(),
        )
    });
    for ttl in [request_ttl, instance_ttl] {
        assert!(ttl >= BUMP_THRESHOLD, "ttl {} below threshold", ttl);
        assert!(ttl >= BUMP_TO - 1, "ttl {} below the bump floor", ttl);
    }

    // Age the ledger past the bump threshold, then write again via post_bond.
    let start_seq = ctx.env.ledger().sequence();
    ctx.env
        .ledger()
        .set_sequence_number(start_seq + 100 * DAY_IN_LEDGERS);

    let aged_ttl = ctx.env.as_contract(&ctx.contract_id, || {
        ctx.env.storage().persistent().get_ttl(&key)
    });
    assert!(
        aged_ttl < BUMP_THRESHOLD,
        "aged ttl {} should have dropped below the threshold",
        aged_ttl
    );

    client.post_bond(&ctx.auditor, &id);

    let (bumped_ttl, bumped_instance) = ctx.env.as_contract(&ctx.contract_id, || {
        (
            ctx.env.storage().persistent().get_ttl(&key),
            ctx.env.storage().instance().get_ttl(),
        )
    });
    assert!(
        bumped_ttl > aged_ttl && bumped_ttl >= BUMP_TO - 1,
        "post_bond must re-extend the TTL: {} -> {}",
        aged_ttl,
        bumped_ttl
    );
    assert!(bumped_instance >= BUMP_TO - 1);
}

#[test]
fn test_ttl_extended_on_settle() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    let key = StorageKey::Request(id);

    let start_seq = ctx.env.ledger().sequence();
    ctx.env
        .ledger()
        .set_sequence_number(start_seq + 100 * DAY_IN_LEDGERS);

    let aged_ttl = ctx.env.as_contract(&ctx.contract_id, || {
        ctx.env.storage().persistent().get_ttl(&key)
    });
    assert!(aged_ttl < BUMP_THRESHOLD);

    client.settle(&id);

    let bumped_ttl = ctx.env.as_contract(&ctx.contract_id, || {
        ctx.env.storage().persistent().get_ttl(&key)
    });
    assert!(bumped_ttl >= BUMP_TO - 1 && bumped_ttl > aged_ttl);
}

#[test]
fn test_ttl_extended_on_slash() {
    let ctx = setup();
    let client = ctx.client();
    let id = ctx.bonded_job();
    let key = StorageKey::Request(id);

    let start_seq = ctx.env.ledger().sequence();
    ctx.env
        .ledger()
        .set_sequence_number(start_seq + 100 * DAY_IN_LEDGERS);

    let aged_ttl = ctx.env.as_contract(&ctx.contract_id, || {
        ctx.env.storage().persistent().get_ttl(&key)
    });
    assert!(aged_ttl < BUMP_THRESHOLD);

    client.slash(&id, &ctx.reporter);

    let bumped_ttl = ctx.env.as_contract(&ctx.contract_id, || {
        ctx.env.storage().persistent().get_ttl(&key)
    });
    assert!(bumped_ttl >= BUMP_TO - 1 && bumped_ttl > aged_ttl);
}
