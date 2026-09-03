//! STE-12 — cross-contract integration tests.
//!
//! Every unit test in `contracts/{registry,escrow,tokens}/src/test.rs` exercises
//! one contract in isolation (133 tests, 97%+ line coverage). What none of them
//! can prove is the **wiring**: that money in the escrow, the verdict in the
//! registry and the soulbound badge in the tokens contract stay consistent with
//! each other across a whole audit lifecycle.
//!
//! So these tests deploy all four moving parts into a single `Env`
//! (USDC SAC + `SkillRegistry` + `UsdcEscrow` + `SterishTokens`) and drive them
//! through the real flows:
//!
//! * `test_full_safe_flow_*`         — register → fund → bond → Safe → badge → settle
//! * `test_full_dangerous_flow_*`    — register → fund → bond → Dangerous → no badge → slash
//! * `test_license_flow_*`           — x402 license mint on top of a real badge
//! * `test_rugpull_v2_*`             — v1 audited, v2 swapped in: the badge must not follow
//! * `test_two_parallel_jobs_*`      — one shared USDC pot, two jobs, no cross-contamination
//! * plus the cross-contract guard set (auth, hash miss, roles, double settle)
//!
//! Money rule of this file: **every test that moves USDC asserts the balance of
//! every actor plus the escrow contract**, so a leak has nowhere to hide.

use core::cell::Cell;
use soroban_sdk::{
    testutils::{Address as _, MockAuth, MockAuthInvoke},
    token::{StellarAssetClient, TokenClient},
    Address, BytesN, Env, IntoVal, String,
};
use sterish_escrow::{AuditStatus, EscrowError, UsdcEscrow, UsdcEscrowClient};
use sterish_registry::{AuditVerdict, SkillRegistry, SkillRegistryClient};
use sterish_tokens::{SterishTokens, SterishTokensClient, TokenError};

/// Audit fee escrowed by the requestor (5 USDC at 7 decimals).
const FEE: i128 = 5_000_000;
/// Bond locked by the auditor (3 USDC).
const BOND: i128 = 3_000_000;
/// Opening USDC balance handed to every funded actor (10 USDC).
const MINT: i128 = 10_000_000;

/// Assert that a `try_*` call returned our typed contract error (not a host panic).
macro_rules! assert_err {
    ($res:expr, $want:expr) => {
        match $res {
            Err(Ok(e)) => assert_eq!(e, $want),
            other => panic!("expected {:?}, got {:?}", $want, other),
        }
    };
}

/// The whole Sterish system in one `Env`.
struct World {
    env: Env,
    /// The USDC SAC every payment settles in.
    usdc: Address,
    registry_id: Address,
    escrow_id: Address,
    tokens_id: Address,

    /// Deployer / operator: registry admin, escrow admin (settle & slash).
    admin: Address,
    /// Auditor role on BOTH the registry (writes verdicts) and the tokens
    /// contract (mints the VERIFIED badge). Also the party that bonds jobs.
    auditor: Address,
    /// The x402 seller backend, the only address allowed to mint licenses.
    minter: Address,
    /// Skill developer — owns the registry entry, receives the badge.
    skill_owner: Address,
    /// Party that pays for the audit.
    requestor: Address,
    /// Buying agent — receives a license.
    agent: Address,
    /// Whoever reports a bad audit and collects the slashed bond.
    reporter: Address,

    /// Nonce so every content/evidence hash in a test is distinct (the registry
    /// rejects hash reuse with `HashAlreadyRegistered`).
    hash_nonce: Cell<u8>,
}

impl World {
    // -- clients ------------------------------------------------------------

    fn registry(&self) -> SkillRegistryClient<'_> {
        SkillRegistryClient::new(&self.env, &self.registry_id)
    }

    fn escrow(&self) -> UsdcEscrowClient<'_> {
        UsdcEscrowClient::new(&self.env, &self.escrow_id)
    }

    fn tokens(&self) -> SterishTokensClient<'_> {
        SterishTokensClient::new(&self.env, &self.tokens_id)
    }

    fn token(&self) -> TokenClient<'_> {
        TokenClient::new(&self.env, &self.usdc)
    }

    // -- money helpers ------------------------------------------------------

    fn bal(&self, who: &Address) -> i128 {
        self.token().balance(who)
    }

    /// USDC held by the escrow contract itself. All jobs share this one pot, so
    /// it is the invariant every money test checks.
    fn escrowed(&self) -> i128 {
        self.bal(&self.escrow_id)
    }

    fn mint_usdc(&self, to: &Address, amount: i128) {
        StellarAssetClient::new(&self.env, &self.usdc).mint(to, &amount);
    }

    /// A brand-new address holding `amount` USDC.
    fn funded(&self, amount: i128) -> Address {
        let who = Address::generate(&self.env);
        self.mint_usdc(&who, amount);
        who
    }

    // -- misc helpers -------------------------------------------------------

    fn s(&self, text: &str) -> String {
        String::from_str(&self.env, text)
    }

    fn skill(&self) -> String {
        self.s("com.example.send-email")
    }

    fn v1(&self) -> String {
        self.s("1.0.0")
    }

    fn v2(&self) -> String {
        self.s("2.0.0")
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

    /// Register `(skill, version)` under `skill_owner`; returns the content hash.
    fn register(&self, version: &String) -> BytesN<32> {
        let h = self.next_hash();
        self.registry()
            .register_skill(&self.skill_owner, &self.skill(), version, &h);
        h
    }

    /// Write a verdict for `(skill, version)` as the auditor.
    fn audit(&self, version: &String, verdict: AuditVerdict, score: u32) -> BytesN<32> {
        let evidence = self.next_hash();
        self.registry()
            .submit_verdict(&self.skill(), version, &verdict, &score, &evidence);
        evidence
    }

    /// Open a job for `version` and have the auditor bond it. Returns the id.
    fn bonded_job(&self, version: &String) -> u32 {
        let escrow = self.escrow();
        let id = escrow.create_audit_request(&self.requestor, &self.skill(), version, &FEE, &BOND);
        escrow.post_bond(&self.auditor, &id);
        id
    }

    /// register → job → bond → `Safe` verdict → VERIFIED badge → settle.
    /// The complete happy path, reused by the tests that build on top of it.
    fn full_safe_flow(&self, version: &String) -> (BytesN<32>, u32, u32) {
        let content_hash = self.register(version);
        let request_id = self.bonded_job(version);
        self.audit(version, AuditVerdict::Safe, 92);
        let token_id = self
            .tokens()
            .mint_verified(&self.skill(), version, &self.skill_owner);
        self.escrow().settle(&request_id);
        (content_hash, request_id, token_id)
    }
}

/// Deploy the USDC SAC, the registry, the escrow and the tokens contract wired
/// to each other, fund the requestor and the auditor, and mock every auth.
///
/// Tests that are *about* authorization override this per call with
/// `client.mock_auths(..)`, exactly like the per-contract unit tests do.
fn setup() -> World {
    let env = Env::default();
    env.mock_all_auths();

    let issuer = Address::generate(&env);
    let usdc = env.register_stellar_asset_contract_v2(issuer).address();

    let admin = Address::generate(&env);
    let auditor = Address::generate(&env);
    let minter = Address::generate(&env);
    let skill_owner = Address::generate(&env);
    let requestor = Address::generate(&env);
    let agent = Address::generate(&env);
    let reporter = Address::generate(&env);

    let registry_id = env.register(SkillRegistry, (admin.clone(), auditor.clone()));
    let escrow_id = env.register(UsdcEscrow, (usdc.clone(), admin.clone()));
    let tokens_id = env.register(
        SterishTokens,
        (
            admin.clone(),
            registry_id.clone(),
            auditor.clone(),
            minter.clone(),
        ),
    );

    let sac = StellarAssetClient::new(&env, &usdc);
    sac.mint(&requestor, &MINT);
    sac.mint(&auditor, &MINT);

    World {
        env,
        usdc,
        registry_id,
        escrow_id,
        tokens_id,
        admin,
        auditor,
        minter,
        skill_owner,
        requestor,
        agent,
        reporter,
        hash_nonce: Cell::new(0),
    }
}

/// Assert the full money picture in one shot: requestor, auditor, reporter,
/// skill owner, agent and the escrow pot. `who` names the step in the failure.
fn assert_balances(w: &World, step: &str, requestor: i128, auditor: i128, escrowed: i128) {
    assert_eq!(w.bal(&w.requestor), requestor, "{step}: requestor balance");
    assert_eq!(w.bal(&w.auditor), auditor, "{step}: auditor balance");
    assert_eq!(w.escrowed(), escrowed, "{step}: escrowed balance");
    // Parties that never touch USDC in these flows must stay at zero.
    assert_eq!(w.bal(&w.skill_owner), 0, "{step}: skill owner balance");
    assert_eq!(w.bal(&w.agent), 0, "{step}: agent balance");
    // Nothing is ever created or destroyed: the two funded actors started with
    // MINT each and the pot holds whatever left their wallets.
    assert_eq!(
        w.bal(&w.requestor) + w.bal(&w.auditor) + w.escrowed() + w.bal(&w.reporter),
        2 * MINT,
        "{step}: USDC conservation"
    );
}

// ===========================================================================
// 0. Deployment wiring — the addresses each contract was constructed with
// ===========================================================================

#[test]
fn test_all_three_contracts_are_wired_to_each_other() {
    let w = setup();
    let (registry, escrow, tokens) = (w.registry(), w.escrow(), w.tokens());

    // Registry: operator is admin, the pipeline operator holds the auditor role.
    assert_eq!(registry.get_admin(), w.admin);
    assert_eq!(registry.get_auditor(), w.auditor);
    assert_eq!(registry.get_skill_count(), 0);

    // Escrow: settles in the USDC SAC, admin gated for settle/slash.
    assert_eq!(escrow.get_usdc_token(), w.usdc);
    assert_eq!(escrow.get_admin(), w.admin);
    assert_eq!(escrow.get_request_count(), 0);

    // Tokens: the Safe gate points at THIS registry (immutable, no setter), the
    // auditor role is the same actor that writes verdicts, and the minter role
    // is the separate x402 seller backend.
    assert_eq!(tokens.get_admin(), w.admin);
    assert_eq!(
        tokens.get_registry(),
        w.registry_id,
        "the badge gate must consult the registry we deployed"
    );
    assert_eq!(tokens.get_auditor_role(), w.auditor);
    assert_eq!(tokens.get_minter_role(), w.minter);
    assert_ne!(
        tokens.get_minter_role(),
        tokens.get_auditor_role(),
        "badge minting and licence selling are separate roles"
    );
    assert_eq!(tokens.total_supply(), 0);

    assert_balances(&w, "fresh deployment", MINT, MINT, 0);
}

// ===========================================================================
// A. The full SAFE lifecycle, step by step, with balances checked at each step
// ===========================================================================

#[test]
fn test_full_safe_flow_register_fund_bond_verdict_mint_settle() {
    let w = setup();
    let (registry, escrow, tokens) = (w.registry(), w.escrow(), w.tokens());
    let skill = w.skill();
    let version = w.v1();

    assert_balances(&w, "start", MINT, MINT, 0);

    // 1. The developer registers version 1.0.0 of their skill.
    let content_hash = w.register(&version);
    assert_eq!(registry.get_skill_count(), 1);
    assert_eq!(
        registry.get_version(&skill, &version).verdict,
        AuditVerdict::Unaudited,
        "a freshly registered version starts Unaudited"
    );
    assert!(!registry.is_verified(&skill, &version));
    assert_balances(&w, "after register", MINT, MINT, 0);

    // 2. Someone pays for the audit: the fee leaves their wallet immediately.
    let request_id = escrow.create_audit_request(&w.requestor, &skill, &version, &FEE, &BOND);
    assert_eq!(request_id, 1);
    assert_balances(&w, "after create_audit_request", MINT - FEE, MINT, FEE);
    let request = escrow.get_request(&request_id);
    assert_eq!(request.status, AuditStatus::Open);
    assert_eq!(request.auditor, None, "nobody has taken the job yet");
    assert_eq!(request.skill_id, skill);
    assert_eq!(request.version, version);

    // 3. The auditor takes the job by locking exactly the agreed bond.
    escrow.post_bond(&w.auditor, &request_id);
    assert_balances(&w, "after post_bond", MINT - FEE, MINT - BOND, FEE + BOND);
    let request = escrow.get_request(&request_id);
    assert_eq!(request.status, AuditStatus::Bonded);
    assert_eq!(request.auditor, Some(w.auditor.clone()));

    // 4. The pipeline verdict lands on THIS version.
    let evidence = w.audit(&version, AuditVerdict::Safe, 92);
    assert!(registry.is_verified(&skill, &version));
    let record = registry.get_version(&skill, &version);
    assert_eq!(record.verdict, AuditVerdict::Safe);
    assert_eq!(record.trust_score, 92);
    assert_eq!(record.auditor, Some(w.auditor.clone()));
    assert_eq!(record.evidence_hash, evidence);
    // A verdict moves no money.
    assert_balances(
        &w,
        "after submit_verdict",
        MINT - FEE,
        MINT - BOND,
        FEE + BOND,
    );

    // 5. Only now can the VERIFIED badge be minted, and it goes to the owner.
    let token_id = tokens.mint_verified(&skill, &version, &w.skill_owner);
    assert_eq!(token_id, 1, "token ids start at 1");
    assert!(tokens.is_verified_token(&skill, &version));
    assert_eq!(
        tokens.owner_of(&token_id),
        w.skill_owner,
        "the badge belongs to the skill owner, not to the auditor"
    );
    assert_eq!(tokens.total_supply(), 1);
    assert_balances(
        &w,
        "after mint_verified",
        MINT - FEE,
        MINT - BOND,
        FEE + BOND,
    );

    // 6. The operator settles: the honest auditor collects fee + bond back.
    escrow.settle(&request_id);
    assert_eq!(escrow.get_request(&request_id).status, AuditStatus::Settled);
    assert_balances(&w, "after settle", MINT - FEE, MINT + FEE, 0);

    // 7. Final cross-contract state.
    assert_eq!(w.bal(&w.requestor), MINT - FEE, "requestor paid the fee");
    assert_eq!(w.bal(&w.auditor), MINT + FEE, "auditor earned the fee");
    assert_eq!(w.bal(&w.reporter), 0, "no reporter in the happy path");
    assert_eq!(w.bal(&w.skill_owner), 0);
    assert_eq!(w.bal(&w.agent), 0);
    assert_eq!(w.escrowed(), 0, "the escrow pot is empty again");

    let looked_up = registry
        .lookup_by_hash(&content_hash)
        .expect("the audited artifact resolves by its content hash");
    assert_eq!(looked_up.verdict, AuditVerdict::Safe);
    assert_eq!(looked_up.skill_id, skill);
    assert_eq!(looked_up.version, version);
    assert!(tokens.is_verified_token(&skill, &version));
    assert_eq!(tokens.total_supply(), 1);
}

// ===========================================================================
// B. The full DANGEROUS lifecycle: no badge, no license, bond to the reporter
// ===========================================================================

#[test]
fn test_full_dangerous_flow_no_badge_and_slash_pays_reporter() {
    let w = setup();
    let (registry, escrow, tokens) = (w.registry(), w.escrow(), w.tokens());
    let skill = w.skill();
    let version = w.v1();

    let content_hash = w.register(&version);
    let request_id = w.bonded_job(&version);
    assert_balances(&w, "after post_bond", MINT - FEE, MINT - BOND, FEE + BOND);

    // The pipeline found a poisoned skill.
    w.audit(&version, AuditVerdict::Dangerous, 5);
    assert!(
        !registry.is_verified(&skill, &version),
        "Dangerous is never verified"
    );

    // The badge gate is a live cross-contract call, so it rejects this.
    assert_err!(
        tokens.try_mint_verified(&skill, &version, &w.skill_owner),
        TokenError::NotSafeVerdict
    );
    assert!(!tokens.is_verified_token(&skill, &version));
    assert_eq!(tokens.total_supply(), 0, "nothing was minted");

    // And with no badge there is nothing to license either.
    assert_err!(
        tokens.try_mint_license(&w.agent, &skill, &version),
        TokenError::NotVerified
    );
    assert!(!tokens.has_license(&w.agent, &skill, &version));
    assert_eq!(tokens.total_supply(), 0);

    // The bad audit is reported: bond to the reporter, fee back to who paid it.
    escrow.slash(&request_id, &w.reporter);
    assert_eq!(escrow.get_request(&request_id).status, AuditStatus::Slashed);

    assert_eq!(w.bal(&w.reporter), BOND, "the reporter collects the bond");
    assert_eq!(w.bal(&w.requestor), MINT, "the requestor is made whole");
    assert_eq!(w.bal(&w.auditor), MINT - BOND, "the auditor lost the bond");
    assert_eq!(w.bal(&w.skill_owner), 0);
    assert_eq!(w.bal(&w.agent), 0);
    assert_eq!(w.escrowed(), 0, "the escrow pot is empty");
    assert_balances(&w, "after slash", MINT, MINT - BOND, 0);

    // Final registry/token state: still Dangerous, still unbadged.
    assert_eq!(
        registry.lookup_by_hash(&content_hash).unwrap().verdict,
        AuditVerdict::Dangerous
    );
    assert!(!tokens.is_verified_token(&skill, &version));
    assert_eq!(tokens.total_supply(), 0);
}

// ===========================================================================
// C. The x402 license, on top of a real badge
// ===========================================================================

#[test]
fn test_license_flow_after_verified_badge() {
    let w = setup();
    let tokens = w.tokens();
    let skill = w.skill();
    let version = w.v1();

    let (_, _, badge_id) = w.full_safe_flow(&version);
    assert_eq!(badge_id, 1);

    // The x402 seller backend mints the license once payment settles off-chain.
    let license_id = tokens.mint_license(&w.agent, &skill, &version);
    assert_eq!(license_id, 2);
    assert!(tokens.has_license(&w.agent, &skill, &version));
    assert_eq!(tokens.owner_of(&license_id), w.agent);
    assert_eq!(tokens.total_supply(), 2, "one badge plus one license");

    // A second agent that never bought anything holds no license.
    let other_agent = Address::generate(&w.env);
    assert!(
        !tokens.has_license(&other_agent, &skill, &version),
        "a licence is per agent, it is not a public flag"
    );

    // Licensing is an off-chain (x402) payment; it moves no escrow USDC.
    assert_balances(&w, "after mint_license", MINT - FEE, MINT + FEE, 0);
}

// ===========================================================================
// D. Cross-contract guards
// ===========================================================================

#[test]
fn test_register_without_auth_reverts() {
    let w = setup();
    let registry = w.registry();
    let attacker = Address::generate(&w.env);
    let skill = w.skill();
    let version = w.v1();
    let h = w.next_hash();

    // Only the attacker signed; the call claims to be the skill owner.
    let res = registry
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &w.registry_id,
                fn_name: "register_skill",
                args: (attacker.clone(), skill.clone(), version.clone(), h.clone())
                    .into_val(&w.env),
                sub_invokes: &[],
            },
        }])
        .try_register_skill(&w.skill_owner, &skill, &version, &h);

    assert!(
        res.is_err(),
        "register_skill must reject a missing owner auth"
    );
    assert_eq!(registry.get_skill_count(), 0, "nothing was written");
    assert!(registry.lookup_by_hash(&h).is_none());
    // And the downstream contracts see nothing either.
    assert!(!w.tokens().is_verified_token(&skill, &version));
}

#[test]
fn test_submit_verdict_by_non_auditor_reverts() {
    let w = setup();
    let (registry, tokens) = (w.registry(), w.tokens());
    let skill = w.skill();
    let version = w.v1();
    w.register(&version);
    let evidence = w.next_hash();

    // The skill owner tries to grade their own skill.
    let res = registry
        .mock_auths(&[MockAuth {
            address: &w.skill_owner,
            invoke: &MockAuthInvoke {
                contract: &w.registry_id,
                fn_name: "submit_verdict",
                args: (
                    skill.clone(),
                    version.clone(),
                    AuditVerdict::Safe,
                    100u32,
                    evidence.clone(),
                )
                    .into_val(&w.env),
                sub_invokes: &[],
            },
        }])
        .try_submit_verdict(&skill, &version, &AuditVerdict::Safe, &100, &evidence);

    assert!(
        res.is_err(),
        "submit_verdict must require the auditor's auth"
    );
    assert!(!registry.is_verified(&skill, &version));
    // The badge gate reads the registry live, so it still refuses.
    assert_err!(
        tokens.try_mint_verified(&skill, &version, &w.skill_owner),
        TokenError::NotSafeVerdict
    );
    assert_eq!(tokens.total_supply(), 0);
}

#[test]
fn test_lookup_by_hash_one_byte_miss() {
    let w = setup();
    let registry = w.registry();
    let version = w.v1();

    let content_hash = w.register(&version);
    w.audit(&version, AuditVerdict::Safe, 92);

    // Flip exactly one byte of the audited artifact's hash.
    let mut tampered = content_hash.to_array();
    tampered[31] ^= 0x01;
    let tampered = BytesN::from_array(&w.env, &tampered);
    assert_ne!(tampered, content_hash);

    assert!(
        registry.lookup_by_hash(&content_hash).is_some(),
        "the exact artifact still resolves"
    );
    assert!(
        registry.lookup_by_hash(&tampered).is_none(),
        "a one-byte-different artifact must resolve to nothing, \
         never to the audited version's Safe verdict"
    );
}

#[test]
fn test_mint_without_role_reverts() {
    let w = setup();
    let tokens = w.tokens();
    let skill = w.skill();
    let version = w.v1();
    w.register(&version);
    w.audit(&version, AuditVerdict::Safe, 92);

    // 1. Badge: signed by someone who is not the auditor role.
    let attacker = Address::generate(&w.env);
    let res = tokens
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &w.tokens_id,
                fn_name: "mint_verified",
                args: (skill.clone(), version.clone(), attacker.clone()).into_val(&w.env),
                sub_invokes: &[],
            },
        }])
        .try_mint_verified(&skill, &version, &w.skill_owner);
    assert!(res.is_err(), "mint_verified must require the auditor role");
    assert!(!tokens.is_verified_token(&skill, &version));
    assert_eq!(tokens.total_supply(), 0);

    // The real auditor role can.
    tokens.mint_verified(&skill, &version, &w.skill_owner);
    assert_eq!(tokens.total_supply(), 1);

    // 2. License: signed by the auditor, who is NOT the minter role.
    let res = tokens
        .mock_auths(&[MockAuth {
            address: &w.auditor,
            invoke: &MockAuthInvoke {
                contract: &w.tokens_id,
                fn_name: "mint_license",
                args: (w.agent.clone(), skill.clone(), version.clone()).into_val(&w.env),
                sub_invokes: &[],
            },
        }])
        .try_mint_license(&w.agent, &skill, &version);
    assert!(res.is_err(), "mint_license must require the minter role");
    assert!(!tokens.has_license(&w.agent, &skill, &version));
    assert_eq!(tokens.total_supply(), 1, "still just the badge");

    // The real minter role can.
    tokens.mint_license(&w.agent, &skill, &version);
    assert!(tokens.has_license(&w.agent, &skill, &version));
    assert_eq!(tokens.total_supply(), 2);
}

#[test]
fn test_double_settle_reverts() {
    let w = setup();
    let escrow = w.escrow();
    let version = w.v1();

    let (_, request_id, _) = w.full_safe_flow(&version);
    assert_balances(&w, "after first settle", MINT - FEE, MINT + FEE, 0);

    assert_err!(escrow.try_settle(&request_id), EscrowError::AlreadySettled);
    assert_balances(&w, "after second settle attempt", MINT - FEE, MINT + FEE, 0);

    // Slashing a settled job is equally impossible — the pot is empty and the
    // terminal state must not be reachable twice through another door.
    assert_err!(
        escrow.try_slash(&request_id, &w.reporter),
        EscrowError::AlreadySettled
    );
    assert_eq!(w.bal(&w.reporter), 0);
    assert_eq!(escrow.get_request(&request_id).status, AuditStatus::Settled);
    assert_balances(&w, "after slash attempt", MINT - FEE, MINT + FEE, 0);
}

#[test]
fn test_license_does_not_carry_to_new_version() {
    let w = setup();
    let tokens = w.tokens();
    let skill = w.skill();
    let (v1, v2) = (w.v1(), w.v2());

    // v1: audited Safe, badged, licensed to the agent.
    w.full_safe_flow(&v1);
    tokens.mint_license(&w.agent, &skill, &v1);
    assert!(tokens.has_license(&w.agent, &skill, &v1));

    // v2: a genuinely new release, also audited Safe and badged.
    w.register(&v2);
    w.audit(&v2, AuditVerdict::Safe, 90);
    tokens.mint_verified(&skill, &v2, &w.skill_owner);
    assert!(tokens.is_verified_token(&skill, &v2));

    // The licence bought for v1 does NOT unlock v2.
    assert!(
        !tokens.has_license(&w.agent, &skill, &v2),
        "a licence is bound to one exact version"
    );
    assert!(
        tokens.has_license(&w.agent, &skill, &v1),
        "and the v1 licence is untouched"
    );
    assert_eq!(tokens.total_supply(), 3, "badge v1 + licence v1 + badge v2");
}

// ===========================================================================
// E. Rug pull: v1 is audited, v2 is swapped in unaudited
// ===========================================================================

#[test]
fn test_rugpull_v2_across_all_three_contracts() {
    let w = setup();
    let (registry, tokens) = (w.registry(), w.tokens());
    let skill = w.skill();
    let (v1, v2) = (w.v1(), w.v2());

    // v1 is the honest release: audited Safe, badged, and sold to an agent.
    let (h1, _, _) = w.full_safe_flow(&v1);
    tokens.mint_license(&w.agent, &skill, &v1);
    assert!(tokens.has_license(&w.agent, &skill, &v1));

    // v2 is the rug pull: same skill_id, different code, never audited.
    let h2 = w.register(&v2);
    assert_ne!(h1, h2, "different code means a different content hash");

    // Registry: the new artifact resolves to itself, and it is Unaudited.
    let looked_up = registry
        .lookup_by_hash(&h2)
        .expect("v2 is registered, so its hash resolves");
    assert_eq!(looked_up.version, v2);
    assert_eq!(
        looked_up.verdict,
        AuditVerdict::Unaudited,
        "v2 must not inherit v1's Safe verdict"
    );
    assert!(!registry.is_verified(&skill, &v2));
    // v1 is untouched.
    assert_eq!(
        registry.lookup_by_hash(&h1).unwrap().verdict,
        AuditVerdict::Safe
    );

    // Tokens: no badge for v2, and the badge for v1 does not answer for it.
    assert!(!tokens.is_verified_token(&skill, &v2));
    assert!(tokens.is_verified_token(&skill, &v1));
    assert_err!(
        tokens.try_mint_verified(&skill, &v2, &w.skill_owner),
        TokenError::NotSafeVerdict
    );

    // And nobody can buy a licence for the rug-pulled version.
    let agent2 = Address::generate(&w.env);
    assert_err!(
        tokens.try_mint_license(&agent2, &skill, &v2),
        TokenError::NotVerified
    );
    assert!(!tokens.has_license(&agent2, &skill, &v2));
    assert!(
        !tokens.has_license(&w.agent, &skill, &v2),
        "the v1 buyer is not licensed for v2 either"
    );
    assert_eq!(tokens.total_supply(), 2, "still only badge v1 + licence v1");
}

// ===========================================================================
// F. Fund isolation between two concurrent jobs sharing one USDC pot
// ===========================================================================

#[test]
fn test_two_parallel_jobs_do_not_touch_each_other_funds() {
    let w = setup();
    let (registry, escrow, tokens) = (w.registry(), w.escrow(), w.tokens());

    // Two independent skills, two requestors, two auditors, different amounts.
    let skill_a = w.s("com.example.alpha");
    let skill_b = w.s("com.example.beta");
    let version = w.v1();

    let owner_a = Address::generate(&w.env);
    let owner_b = Address::generate(&w.env);
    let requestor_a = w.funded(MINT);
    let requestor_b = w.funded(MINT);
    let auditor_a = w.funded(MINT);
    let auditor_b = w.funded(MINT);

    // The registry auditor role is shared (one operator), the escrow bonds are not.
    registry.register_skill(&owner_a, &skill_a, &version, &w.next_hash());
    registry.register_skill(&owner_b, &skill_b, &version, &w.next_hash());

    let fee_a = FEE;
    let bond_a = BOND;
    let fee_b = 1_500_000i128;
    let bond_b = 900_000i128;

    let job_a = escrow.create_audit_request(&requestor_a, &skill_a, &version, &fee_a, &bond_a);
    let job_b = escrow.create_audit_request(&requestor_b, &skill_b, &version, &fee_b, &bond_b);
    assert_ne!(job_a, job_b);
    assert_eq!(w.escrowed(), fee_a + fee_b);

    escrow.post_bond(&auditor_a, &job_a);
    escrow.post_bond(&auditor_b, &job_b);
    assert_eq!(w.escrowed(), fee_a + bond_a + fee_b + bond_b);
    assert_eq!(w.bal(&auditor_a), MINT - bond_a);
    assert_eq!(w.bal(&auditor_b), MINT - bond_b);

    // Job A ends well, job B ends badly.
    registry.submit_verdict(&skill_a, &version, &AuditVerdict::Safe, &95, &w.next_hash());
    registry.submit_verdict(
        &skill_b,
        &version,
        &AuditVerdict::Dangerous,
        &3,
        &w.next_hash(),
    );

    tokens.mint_verified(&skill_a, &version, &owner_a);
    assert_err!(
        tokens.try_mint_verified(&skill_b, &version, &owner_b),
        TokenError::NotSafeVerdict
    );

    // Settling A must not consume one stroop of B's escrowed money.
    escrow.settle(&job_a);
    assert_eq!(
        w.bal(&auditor_a),
        MINT - bond_a + fee_a + bond_a,
        "auditor A collected exactly job A's fee + bond"
    );
    assert_eq!(w.bal(&auditor_b), MINT - bond_b, "auditor B untouched");
    assert_eq!(
        w.escrowed(),
        fee_b + bond_b,
        "job B's money is still fully escrowed"
    );
    assert_eq!(w.bal(&requestor_a), MINT - fee_a);
    assert_eq!(w.bal(&requestor_b), MINT - fee_b);
    assert_eq!(escrow.get_request(&job_b).status, AuditStatus::Bonded);

    // Slashing B pays B's bond only, and refunds B's fee only.
    escrow.slash(&job_b, &w.reporter);
    assert_eq!(w.bal(&w.reporter), bond_b, "reporter got job B's bond only");
    assert_eq!(w.bal(&requestor_b), MINT, "requestor B was refunded");
    assert_eq!(w.bal(&requestor_a), MINT - fee_a, "requestor A untouched");
    assert_eq!(w.bal(&auditor_b), MINT - bond_b, "auditor B lost the bond");
    assert_eq!(w.bal(&auditor_a), MINT + fee_a);
    assert_eq!(w.escrowed(), 0, "the shared pot is empty and balanced");

    // Conservation across the four funded actors plus the reporter.
    assert_eq!(
        w.bal(&requestor_a)
            + w.bal(&requestor_b)
            + w.bal(&auditor_a)
            + w.bal(&auditor_b)
            + w.bal(&w.reporter),
        4 * MINT,
        "no USDC was created or destroyed"
    );

    assert_eq!(escrow.get_request(&job_a).status, AuditStatus::Settled);
    assert_eq!(escrow.get_request(&job_b).status, AuditStatus::Slashed);
    assert!(tokens.is_verified_token(&skill_a, &version));
    assert!(!tokens.is_verified_token(&skill_b, &version));
    assert_eq!(tokens.total_supply(), 1);
}
