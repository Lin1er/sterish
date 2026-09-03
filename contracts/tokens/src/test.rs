#![cfg(test)]
extern crate std;

use crate::{
    data::{BUMP_THRESHOLD, BUMP_TO, DAY_IN_LEDGERS},
    DataKey, LicenseMinted, SterishTokens, SterishTokensClient, TokenError, TokenKind, TokenRecord,
    VerifiedMinted,
};
use core::cell::Cell;
use soroban_sdk::{
    testutils::{
        storage::{Instance as _, Persistent as _},
        Address as _, Events as _, Ledger, MockAuth, MockAuthInvoke,
    },
    Address, BytesN, Env, Event, IntoVal, String,
};
use sterish_registry::{AuditVerdict, SkillRegistry, SkillRegistryClient};

/// Assert that a `try_*` call returned our typed contract error.
macro_rules! assert_token_err {
    ($res:expr, $want:expr) => {
        match $res {
            Err(Ok(e)) => assert_eq!(e, $want),
            other => std::panic!("expected {:?}, got {:?}", $want, other),
        }
    };
}

struct Ctx {
    env: Env,
    tokens_id: Address,
    registry_id: Address,
    admin: Address,
    /// Auditor role on BOTH contracts: the same real-world actor writes the
    /// verdict into the registry and mints the badge here.
    auditor: Address,
    /// The x402 seller backend that mints licenses.
    minter: Address,
    /// Skill owner — the party a VERIFIED badge is minted to.
    owner: Address,
    /// Buying agent — the party a license is minted to.
    agent: Address,
    /// Nonce so every seeded version gets a distinct content_hash (the registry
    /// rejects hash reuse with `HashAlreadyRegistered`).
    hash_nonce: Cell<u8>,
}

impl Ctx {
    fn client(&self) -> SterishTokensClient<'_> {
        SterishTokensClient::new(&self.env, &self.tokens_id)
    }

    fn registry(&self) -> SkillRegistryClient<'_> {
        SkillRegistryClient::new(&self.env, &self.registry_id)
    }

    fn next_hash(&self) -> BytesN<32> {
        let n = self.hash_nonce.get().wrapping_add(1);
        self.hash_nonce.set(n);
        let mut arr = [0u8; 32];
        arr[0] = n;
        arr[13] = n.wrapping_mul(3).wrapping_add(11);
        arr[31] = n.wrapping_add(7);
        BytesN::from_array(&self.env, &arr)
    }

    /// Register `(skill_id, version)` in the REAL registry, owned by `self.owner`.
    fn register(&self, skill_id: &String, version: &String) {
        self.registry()
            .register_skill(&self.owner, skill_id, version, &self.next_hash());
    }

    /// Register and audit `(skill_id, version)` with `verdict`.
    fn seed(&self, skill_id: &String, version: &String, verdict: AuditVerdict) {
        self.register(skill_id, version);
        let score = match verdict {
            AuditVerdict::Safe => 92u32,
            AuditVerdict::Warning => 55,
            _ => 5,
        };
        self.registry()
            .submit_verdict(skill_id, version, &verdict, &score, &self.next_hash());
    }

    /// Register + audit `Safe` — the only state that may mint a badge.
    fn seed_safe(&self, skill_id: &String, version: &String) {
        self.seed(skill_id, version, AuditVerdict::Safe);
    }
}

/// Deploy the real registry AND the tokens contract, with all auths mocked.
/// Used by every test that is not about authorization itself; per-call
/// `client.mock_auths(..)` still overrides this for the calls that are.
fn setup() -> Ctx {
    let env = Env::default();
    let admin = Address::generate(&env);
    let auditor = Address::generate(&env);
    let minter = Address::generate(&env);
    let owner = Address::generate(&env);
    let agent = Address::generate(&env);

    let registry_id = env.register(SkillRegistry, (admin.clone(), auditor.clone()));
    let tokens_id = env.register(
        SterishTokens,
        (
            admin.clone(),
            registry_id.clone(),
            auditor.clone(),
            minter.clone(),
        ),
    );
    env.mock_all_auths();

    Ctx {
        env,
        tokens_id,
        registry_id,
        admin,
        auditor,
        minter,
        owner,
        agent,
        hash_nonce: Cell::new(0),
    }
}

fn sid(env: &Env, s: &str) -> String {
    String::from_str(env, s)
}

// ---------------------------------------------------------------------------
// constructor / initial state
// ---------------------------------------------------------------------------

#[test]
fn test_constructor_sets_state() {
    let ctx = setup();
    let client = ctx.client();

    assert_eq!(client.get_admin(), ctx.admin);
    assert_eq!(client.get_registry(), ctx.registry_id);
    assert_eq!(client.get_auditor_role(), ctx.auditor);
    assert_eq!(client.get_minter_role(), ctx.minter);
    assert_eq!(client.total_supply(), 0);
}

#[test]
fn test_total_supply_is_zero_before_any_mint() {
    let ctx = setup();
    let client = ctx.client();
    assert_eq!(client.total_supply(), 0);
    assert!(!client.is_verified_token(&sid(&ctx.env, "x"), &sid(&ctx.env, "1.0.0")));
}

// ---------------------------------------------------------------------------
// mint_verified — happy path
// ---------------------------------------------------------------------------

#[test]
fn test_mint_verified_happy() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);

    let token_id = client.mint_verified(&skill_id, &version, &ctx.owner);

    assert_eq!(token_id, 1, "token ids start at 1");
    assert!(client.is_verified_token(&skill_id, &version));
    assert_eq!(client.owner_of(&token_id), ctx.owner);
    assert_eq!(client.total_supply(), 1);

    let record = client.get_token(&token_id);
    assert_eq!(
        record,
        TokenRecord {
            token_id: 1,
            kind: TokenKind::Verified,
            skill_id: skill_id.clone(),
            version: version.clone(),
            owner: ctx.owner.clone(),
            minted_at: ctx.env.ledger().timestamp(),
        }
    );
}

#[test]
fn test_mint_verified_per_version_ids_increment() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let v1 = sid(&ctx.env, "1.0.0");
    let v2 = sid(&ctx.env, "2.0.0");
    ctx.seed_safe(&skill_id, &v1);
    ctx.seed_safe(&skill_id, &v2);

    assert_eq!(client.mint_verified(&skill_id, &v1, &ctx.owner), 1);
    assert_eq!(client.mint_verified(&skill_id, &v2, &ctx.owner), 2);
    assert_eq!(client.total_supply(), 2);
    assert_eq!(client.get_token(&1).version, v1);
    assert_eq!(client.get_token(&2).version, v2);
}

// ---------------------------------------------------------------------------
// mint_verified — the `Safe`-only gate (the core requirement of this ticket)
// ---------------------------------------------------------------------------

#[test]
fn test_mint_verified_rejected_when_dangerous() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.evil.token-drainer");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed(&skill_id, &version, AuditVerdict::Dangerous);

    assert_token_err!(
        client.try_mint_verified(&skill_id, &version, &ctx.owner),
        TokenError::NotSafeVerdict
    );
    assert!(!client.is_verified_token(&skill_id, &version));
    assert_eq!(client.total_supply(), 0);
}

#[test]
fn test_mint_verified_rejected_when_warning() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.sketchy");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed(&skill_id, &version, AuditVerdict::Warning);

    assert_token_err!(
        client.try_mint_verified(&skill_id, &version, &ctx.owner),
        TokenError::NotSafeVerdict
    );
    assert_eq!(client.total_supply(), 0);
}

#[test]
fn test_mint_verified_rejected_when_unaudited() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    // Registered but no verdict submitted -> registry reports Unaudited.
    ctx.register(&skill_id, &version);

    assert_token_err!(
        client.try_mint_verified(&skill_id, &version, &ctx.owner),
        TokenError::NotSafeVerdict
    );
    assert_eq!(client.total_supply(), 0);
}

#[test]
fn test_mint_verified_rejected_for_unknown_skill() {
    let ctx = setup();
    let client = ctx.client();
    // Never registered anywhere: `is_verified` returns false rather than panicking.
    assert_token_err!(
        client.try_mint_verified(
            &sid(&ctx.env, "com.nobody.ghost"),
            &sid(&ctx.env, "1.0.0"),
            &ctx.owner
        ),
        TokenError::NotSafeVerdict
    );
}

#[test]
fn test_mint_verified_rejected_for_unknown_version_of_known_skill() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let v1 = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &v1);

    // v2 was never registered: auditing v1 must say nothing about v2.
    assert_token_err!(
        client.try_mint_verified(&skill_id, &sid(&ctx.env, "2.0.0"), &ctx.owner),
        TokenError::NotSafeVerdict
    );
}

#[test]
fn test_mint_verified_rejected_after_verdict_flips_away_from_safe() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);

    // Re-audit the same version as Dangerous BEFORE any badge was minted.
    ctx.registry().submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Dangerous,
        &3,
        &ctx.next_hash(),
    );

    assert_token_err!(
        client.try_mint_verified(&skill_id, &version, &ctx.owner),
        TokenError::NotSafeVerdict
    );
}

// ---------------------------------------------------------------------------
// mint_verified — validation and idempotency
// ---------------------------------------------------------------------------

#[test]
fn test_mint_verified_empty_skill_id_rejected() {
    let ctx = setup();
    let client = ctx.client();
    assert_token_err!(
        client.try_mint_verified(&sid(&ctx.env, ""), &sid(&ctx.env, "1.0.0"), &ctx.owner),
        TokenError::InvalidInput
    );
}

#[test]
fn test_mint_verified_empty_version_rejected() {
    let ctx = setup();
    let client = ctx.client();
    assert_token_err!(
        client.try_mint_verified(
            &sid(&ctx.env, "com.example.x"),
            &sid(&ctx.env, ""),
            &ctx.owner
        ),
        TokenError::InvalidInput
    );
}

#[test]
fn test_double_mint_verified_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);

    assert_eq!(client.mint_verified(&skill_id, &version, &ctx.owner), 1);
    assert_token_err!(
        client.try_mint_verified(&skill_id, &version, &ctx.owner),
        TokenError::AlreadyMinted
    );
    // A second attempt with a DIFFERENT owner must not sneak a token in either.
    let other = Address::generate(&ctx.env);
    assert_token_err!(
        client.try_mint_verified(&skill_id, &version, &other),
        TokenError::AlreadyMinted
    );
    assert_eq!(client.total_supply(), 1);
    assert_eq!(client.owner_of(&1), ctx.owner);
}

// ---------------------------------------------------------------------------
// mint_verified — role gating
// ---------------------------------------------------------------------------

#[test]
fn test_mint_verified_requires_auditor_role() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);

    let attacker = Address::generate(&ctx.env);
    let res = client
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "mint_verified",
                args: (skill_id.clone(), version.clone(), ctx.owner.clone()).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_mint_verified(&skill_id, &version, &ctx.owner);

    assert!(
        res.is_err(),
        "only the auditor role may mint a VERIFIED badge"
    );
    assert!(!client.is_verified_token(&skill_id, &version));
    assert_eq!(client.total_supply(), 0);
}

#[test]
fn test_mint_verified_not_authorized_by_skill_owner() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);

    // The skill owner must never be able to badge their own skill.
    let res = client
        .mock_auths(&[MockAuth {
            address: &ctx.owner,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "mint_verified",
                args: (skill_id.clone(), version.clone(), ctx.owner.clone()).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_mint_verified(&skill_id, &version, &ctx.owner);

    assert!(res.is_err());
    assert_eq!(client.total_supply(), 0);
}

#[test]
fn test_mint_verified_auditor_auth_tree() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);

    // Exactly one signature, from the auditor role, with no sub-invocation:
    // reading `is_verified` from the registry needs no authorization.
    let token_id = client
        .mock_auths(&[MockAuth {
            address: &ctx.auditor,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "mint_verified",
                args: (skill_id.clone(), version.clone(), ctx.owner.clone()).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .mint_verified(&skill_id, &version, &ctx.owner);

    assert_eq!(token_id, 1);
}

// ---------------------------------------------------------------------------
// mint_license
// ---------------------------------------------------------------------------

#[test]
fn test_mint_license_happy() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);
    client.mint_verified(&skill_id, &version, &ctx.owner);

    assert!(!client.has_license(&ctx.agent, &skill_id, &version));
    let token_id = client.mint_license(&ctx.agent, &skill_id, &version);

    assert_eq!(token_id, 2, "the badge took id 1");
    assert!(client.has_license(&ctx.agent, &skill_id, &version));
    assert_eq!(client.owner_of(&token_id), ctx.agent);
    assert_eq!(client.total_supply(), 2);
    assert_eq!(
        client.get_token(&token_id),
        TokenRecord {
            token_id: 2,
            kind: TokenKind::License,
            skill_id: skill_id.clone(),
            version: version.clone(),
            owner: ctx.agent.clone(),
            minted_at: ctx.env.ledger().timestamp(),
        }
    );
}

#[test]
fn test_mint_license_without_verified_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    // Audited Safe in the registry, but the badge was never minted here.
    ctx.seed_safe(&skill_id, &version);

    assert_token_err!(
        client.try_mint_license(&ctx.agent, &skill_id, &version),
        TokenError::NotVerified
    );
    assert!(!client.has_license(&ctx.agent, &skill_id, &version));
    assert_eq!(client.total_supply(), 0);
}

#[test]
fn test_mint_license_unknown_skill_rejected() {
    let ctx = setup();
    let client = ctx.client();
    assert_token_err!(
        client.try_mint_license(
            &ctx.agent,
            &sid(&ctx.env, "com.nobody.ghost"),
            &sid(&ctx.env, "1.0.0")
        ),
        TokenError::NotVerified
    );
}

#[test]
fn test_mint_license_empty_input_rejected() {
    let ctx = setup();
    let client = ctx.client();
    assert_token_err!(
        client.try_mint_license(&ctx.agent, &sid(&ctx.env, ""), &sid(&ctx.env, "1.0.0")),
        TokenError::InvalidInput
    );
    assert_token_err!(
        client.try_mint_license(
            &ctx.agent,
            &sid(&ctx.env, "com.example.x"),
            &sid(&ctx.env, "")
        ),
        TokenError::InvalidInput
    );
}

#[test]
fn test_double_mint_license_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);
    client.mint_verified(&skill_id, &version, &ctx.owner);
    client.mint_license(&ctx.agent, &skill_id, &version);

    assert_token_err!(
        client.try_mint_license(&ctx.agent, &skill_id, &version),
        TokenError::AlreadyMinted
    );
    assert_eq!(client.total_supply(), 2);
}

#[test]
fn test_mint_license_requires_minter_role() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);
    client.mint_verified(&skill_id, &version, &ctx.owner);

    // Not even the agent who would receive the license may mint it: only the
    // seller backend, which mints after payment settles.
    for signer in [ctx.agent.clone(), ctx.auditor.clone(), ctx.admin.clone()] {
        let res = client
            .mock_auths(&[MockAuth {
                address: &signer,
                invoke: &MockAuthInvoke {
                    contract: &ctx.tokens_id,
                    fn_name: "mint_license",
                    args: (ctx.agent.clone(), skill_id.clone(), version.clone()).into_val(&ctx.env),
                    sub_invokes: &[],
                },
            }])
            .try_mint_license(&ctx.agent, &skill_id, &version);
        assert!(res.is_err(), "only the minter role may mint a license");
    }
    assert!(!client.has_license(&ctx.agent, &skill_id, &version));
    assert_eq!(client.total_supply(), 1);
}

#[test]
fn test_mint_license_minter_auth_tree() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);
    client.mint_verified(&skill_id, &version, &ctx.owner);

    let token_id = client
        .mock_auths(&[MockAuth {
            address: &ctx.minter,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "mint_license",
                args: (ctx.agent.clone(), skill_id.clone(), version.clone()).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .mint_license(&ctx.agent, &skill_id, &version);

    assert_eq!(token_id, 2);
}

// ---------------------------------------------------------------------------
// license scoping: bound to a version AND to an agent
// ---------------------------------------------------------------------------

#[test]
fn test_license_is_version_bound() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let v1 = sid(&ctx.env, "1.0.0");
    let v2 = sid(&ctx.env, "2.0.0");

    // BOTH versions are audited Safe and BOTH carry a VERIFIED badge...
    ctx.seed_safe(&skill_id, &v1);
    ctx.seed_safe(&skill_id, &v2);
    client.mint_verified(&skill_id, &v1, &ctx.owner);
    client.mint_verified(&skill_id, &v2, &ctx.owner);

    // ...but the agent only ever bought v1.
    client.mint_license(&ctx.agent, &skill_id, &v1);

    assert!(client.has_license(&ctx.agent, &skill_id, &v1));
    assert!(
        !client.has_license(&ctx.agent, &skill_id, &v2),
        "a license must NOT carry over to a new version — the agent pays again"
    );

    // And buying v2 is a separate, additional token.
    let v2_token = client.mint_license(&ctx.agent, &skill_id, &v2);
    assert!(client.has_license(&ctx.agent, &skill_id, &v2));
    assert_eq!(client.get_token(&v2_token).version, v2);
    assert_eq!(client.total_supply(), 4);
}

#[test]
fn test_license_is_agent_bound() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);
    client.mint_verified(&skill_id, &version, &ctx.owner);
    client.mint_license(&ctx.agent, &skill_id, &version);

    let other_agent = Address::generate(&ctx.env);
    assert!(client.has_license(&ctx.agent, &skill_id, &version));
    assert!(
        !client.has_license(&other_agent, &skill_id, &version),
        "one agent's license must not cover another agent"
    );
}

#[test]
fn test_license_is_skill_bound() {
    let ctx = setup();
    let client = ctx.client();
    let a = sid(&ctx.env, "com.example.send-email");
    let b = sid(&ctx.env, "com.example.read-calendar");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&a, &version);
    ctx.seed_safe(&b, &version);
    client.mint_verified(&a, &version, &ctx.owner);
    client.mint_verified(&b, &version, &ctx.owner);
    client.mint_license(&ctx.agent, &a, &version);

    assert!(client.has_license(&ctx.agent, &a, &version));
    assert!(!client.has_license(&ctx.agent, &b, &version));
}

// ---------------------------------------------------------------------------
// views — unknown input must never panic
// ---------------------------------------------------------------------------

#[test]
fn test_has_license_unknown_returns_false() {
    let ctx = setup();
    let client = ctx.client();
    assert!(!client.has_license(
        &ctx.agent,
        &sid(&ctx.env, "com.nobody.ghost"),
        &sid(&ctx.env, "9.9.9")
    ));
    assert!(!client.has_license(&ctx.agent, &sid(&ctx.env, ""), &sid(&ctx.env, "")));
}

#[test]
fn test_is_verified_token_unknown_returns_false() {
    let ctx = setup();
    let client = ctx.client();
    assert!(!client.is_verified_token(&sid(&ctx.env, "com.nobody.ghost"), &sid(&ctx.env, "9.9.9")));
}

#[test]
fn test_owner_of_unknown() {
    let ctx = setup();
    let client = ctx.client();
    assert_token_err!(client.try_owner_of(&0), TokenError::TokenNotFound);
    assert_token_err!(client.try_owner_of(&1), TokenError::TokenNotFound);
    assert_token_err!(client.try_owner_of(&u32::MAX), TokenError::TokenNotFound);
}

#[test]
fn test_get_token_unknown() {
    let ctx = setup();
    let client = ctx.client();
    assert_token_err!(client.try_get_token(&42), TokenError::TokenNotFound);
}

// ---------------------------------------------------------------------------
// role rotation — admin only
// ---------------------------------------------------------------------------

#[test]
fn test_set_auditor_role_admin_only() {
    let ctx = setup();
    let client = ctx.client();
    let new_auditor = Address::generate(&ctx.env);
    let attacker = Address::generate(&ctx.env);

    let res = client
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "set_auditor_role",
                args: (new_auditor.clone(),).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_set_auditor_role(&new_auditor);
    assert!(res.is_err(), "only admin may rotate the auditor role");
    assert_eq!(client.get_auditor_role(), ctx.auditor);

    client
        .mock_auths(&[MockAuth {
            address: &ctx.admin,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "set_auditor_role",
                args: (new_auditor.clone(),).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .set_auditor_role(&new_auditor);
    assert_eq!(client.get_auditor_role(), new_auditor);
}

#[test]
fn test_set_minter_role_admin_only() {
    let ctx = setup();
    let client = ctx.client();
    let new_minter = Address::generate(&ctx.env);
    let attacker = Address::generate(&ctx.env);

    let res = client
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "set_minter_role",
                args: (new_minter.clone(),).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_set_minter_role(&new_minter);
    assert!(res.is_err(), "only admin may rotate the minter role");
    assert_eq!(client.get_minter_role(), ctx.minter);

    client
        .mock_auths(&[MockAuth {
            address: &ctx.admin,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "set_minter_role",
                args: (new_minter.clone(),).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .set_minter_role(&new_minter);
    assert_eq!(client.get_minter_role(), new_minter);
}

#[test]
fn test_rotated_auditor_can_mint_and_old_cannot() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);

    let new_auditor = Address::generate(&ctx.env);
    client.set_auditor_role(&new_auditor);

    // The OLD auditor no longer passes the role check.
    let res = client
        .mock_auths(&[MockAuth {
            address: &ctx.auditor,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "mint_verified",
                args: (skill_id.clone(), version.clone(), ctx.owner.clone()).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_mint_verified(&skill_id, &version, &ctx.owner);
    assert!(
        res.is_err(),
        "the rotated-out auditor must lose minting rights"
    );

    // The NEW one does.
    let token_id = client
        .mock_auths(&[MockAuth {
            address: &new_auditor,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "mint_verified",
                args: (skill_id.clone(), version.clone(), ctx.owner.clone()).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .mint_verified(&skill_id, &version, &ctx.owner);
    assert_eq!(token_id, 1);
}

#[test]
fn test_rotated_minter_can_mint_and_old_cannot() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);
    client.mint_verified(&skill_id, &version, &ctx.owner);

    let new_minter = Address::generate(&ctx.env);
    client.set_minter_role(&new_minter);

    let res = client
        .mock_auths(&[MockAuth {
            address: &ctx.minter,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "mint_license",
                args: (ctx.agent.clone(), skill_id.clone(), version.clone()).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_mint_license(&ctx.agent, &skill_id, &version);
    assert!(
        res.is_err(),
        "the rotated-out minter must lose minting rights"
    );

    client
        .mock_auths(&[MockAuth {
            address: &new_minter,
            invoke: &MockAuthInvoke {
                contract: &ctx.tokens_id,
                fn_name: "mint_license",
                args: (ctx.agent.clone(), skill_id.clone(), version.clone()).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .mint_license(&ctx.agent, &skill_id, &version);
    assert!(client.has_license(&ctx.agent, &skill_id, &version));
}

#[test]
fn test_registry_address_is_immutable() {
    let ctx = setup();
    let client = ctx.client();
    // There is deliberately no `set_registry`: repointing the registry would move
    // the `Safe` gate to a contract the admin controls. The address written at
    // construction is the address forever.
    assert_eq!(client.get_registry(), ctx.registry_id);
}

// ---------------------------------------------------------------------------
// events
// ---------------------------------------------------------------------------

#[test]
fn test_verified_minted_event() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);

    client.mint_verified(&skill_id, &version, &ctx.owner);

    assert_eq!(
        ctx.env.events().all(),
        std::vec![VerifiedMinted {
            skill_id: skill_id.clone(),
            version: version.clone(),
            owner: ctx.owner.clone(),
        }
        .to_xdr(&ctx.env, &ctx.tokens_id)]
    );
}

#[test]
fn test_license_minted_event() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);
    client.mint_verified(&skill_id, &version, &ctx.owner);

    client.mint_license(&ctx.agent, &skill_id, &version);

    assert_eq!(
        ctx.env.events().all(),
        std::vec![LicenseMinted {
            skill_id: skill_id.clone(),
            version: version.clone(),
            agent: ctx.agent.clone(),
        }
        .to_xdr(&ctx.env, &ctx.tokens_id)]
    );
}

#[test]
fn test_no_event_on_rejected_mint() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.evil.token-drainer");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed(&skill_id, &version, AuditVerdict::Dangerous);

    let _ = client.try_mint_verified(&skill_id, &version, &ctx.owner);
    assert_eq!(ctx.env.events().all(), std::vec![]);
}

// ---------------------------------------------------------------------------
// TTL / state archival
// ---------------------------------------------------------------------------

#[test]
fn test_ttl_extended_on_write() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);
    client.mint_verified(&skill_id, &version, &ctx.owner);

    let token_key = DataKey::Token(1);
    let verified_key = DataKey::VerifiedOf(skill_id.clone(), version.clone());

    let (token_ttl, verified_ttl, instance_ttl) = ctx.env.as_contract(&ctx.tokens_id, || {
        (
            ctx.env.storage().persistent().get_ttl(&token_key),
            ctx.env.storage().persistent().get_ttl(&verified_key),
            ctx.env.storage().instance().get_ttl(),
        )
    });
    for ttl in [token_ttl, verified_ttl, instance_ttl] {
        assert!(ttl >= BUMP_THRESHOLD, "ttl {} below threshold", ttl);
        assert!(ttl >= BUMP_TO - 1, "ttl {} below the bump floor", ttl);
    }

    // Age the ledger past the bump threshold.
    let start_seq = ctx.env.ledger().sequence();
    ctx.env
        .ledger()
        .set_sequence_number(start_seq + 100 * DAY_IN_LEDGERS);

    let aged_ttl = ctx.env.as_contract(&ctx.tokens_id, || {
        ctx.env.storage().persistent().get_ttl(&verified_key)
    });
    assert!(
        aged_ttl < BUMP_THRESHOLD,
        "aged ttl {} should have dropped below the threshold",
        aged_ttl
    );

    // Minting a license touches the badge key too, so both get re-extended.
    client.mint_license(&ctx.agent, &skill_id, &version);

    let license_key = DataKey::LicenseOf(ctx.agent.clone(), skill_id.clone(), version.clone());
    let (bumped_verified, license_ttl, bumped_instance) =
        ctx.env.as_contract(&ctx.tokens_id, || {
            (
                ctx.env.storage().persistent().get_ttl(&verified_key),
                ctx.env.storage().persistent().get_ttl(&license_key),
                ctx.env.storage().instance().get_ttl(),
            )
        });
    assert!(
        bumped_verified > aged_ttl && bumped_verified >= BUMP_TO - 1,
        "a write must re-extend the badge TTL: {} -> {}",
        aged_ttl,
        bumped_verified
    );
    assert!(license_ttl >= BUMP_TO - 1);
    assert!(bumped_instance >= BUMP_TO - 1);
}

// ---------------------------------------------------------------------------
// end-to-end: the poisoned-skill gate (FINAL decision in CLAUDE.md)
// ---------------------------------------------------------------------------

#[test]
fn test_dangerous_skill_never_gets_badge_or_license() {
    let ctx = setup();
    let client = ctx.client();
    let evil = sid(&ctx.env, "com.evil.token-drainer");
    let good = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");

    ctx.seed(&evil, &version, AuditVerdict::Dangerous);
    ctx.seed_safe(&good, &version);

    // The registry itself refuses to call it verified.
    assert!(!ctx.registry().is_verified(&evil, &version));

    // No badge...
    assert_token_err!(
        client.try_mint_verified(&evil, &version, &ctx.owner),
        TokenError::NotSafeVerdict
    );
    // ...and therefore no license, no matter who asks.
    assert_token_err!(
        client.try_mint_license(&ctx.agent, &evil, &version),
        TokenError::NotVerified
    );
    assert!(!client.is_verified_token(&evil, &version));
    assert!(!client.has_license(&ctx.agent, &evil, &version));
    assert_eq!(client.total_supply(), 0);

    // The honest skill next to it is unaffected.
    client.mint_verified(&good, &version, &ctx.owner);
    client.mint_license(&ctx.agent, &good, &version);
    assert!(client.has_license(&ctx.agent, &good, &version));
    assert_eq!(client.total_supply(), 2);
}

#[test]
fn test_badge_survives_a_later_dangerous_reaudit_but_registry_disagrees() {
    // Documents the intended MVP behaviour: the badge is a snapshot of the
    // verdict at mint time. There is no burn (soulbound), so a version that is
    // re-audited `Dangerous` keeps its badge on-chain; consumers that need the
    // live answer must read `SkillRegistry::is_verified`. Revocation is a
    // follow-up decision, not a silent gap.
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    ctx.seed_safe(&skill_id, &version);
    client.mint_verified(&skill_id, &version, &ctx.owner);

    ctx.registry().submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Dangerous,
        &1,
        &ctx.next_hash(),
    );

    assert!(!ctx.registry().is_verified(&skill_id, &version));
    assert!(client.is_verified_token(&skill_id, &version));
}
