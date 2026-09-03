#![cfg(test)]
extern crate std;

use crate::{
    data::{BUMP_THRESHOLD, BUMP_TO, DAY_IN_LEDGERS},
    AuditVerdict, DataKey, RegistryError, SkillEntry, SkillRegistered, SkillRegistry,
    SkillRegistryClient, TrustScoreConfig, VerdictFlipped, VersionRecorded, VersionRegistered,
};
use soroban_sdk::{
    testutils::{
        storage::{Instance as _, Persistent as _},
        Address as _, AuthorizedFunction, AuthorizedInvocation, Events as _, Ledger, MockAuth,
        MockAuthInvoke,
    },
    Address, BytesN, Env, Event, IntoVal, String, Symbol,
};

/// Assert that a `try_*` call returned our typed contract error.
macro_rules! assert_registry_err {
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
    admin: Address,
    auditor: Address,
    owner: Address,
}

impl Ctx {
    fn client(&self) -> SkillRegistryClient<'_> {
        SkillRegistryClient::new(&self.env, &self.contract_id)
    }
}

/// Deploy with all auths mocked — used by every test that is not about auth itself.
fn setup() -> Ctx {
    let ctx = setup_no_auth();
    ctx.env.mock_all_auths();
    ctx
}

/// Deploy WITHOUT mocking auths, so `require_auth` is actually enforced.
fn setup_no_auth() -> Ctx {
    let env = Env::default();
    let admin = Address::generate(&env);
    let auditor = Address::generate(&env);
    let owner = Address::generate(&env);
    let contract_id = env.register(SkillRegistry, (admin.clone(), auditor.clone()));
    Ctx {
        env,
        contract_id,
        admin,
        auditor,
        owner,
    }
}

fn sid(env: &Env, s: &str) -> String {
    String::from_str(env, s)
}

fn hash(env: &Env, byte: u8) -> BytesN<32> {
    let mut arr = [0u8; 32];
    arr[0] = byte;
    arr[17] = byte.wrapping_add(7);
    arr[31] = byte;
    BytesN::from_array(env, &arr)
}

/// Flip exactly one bit of one byte — the "recompiled artifact" scenario.
fn flip_one_byte(env: &Env, h: &BytesN<32>) -> BytesN<32> {
    let mut arr = h.to_array();
    arr[17] ^= 0x01;
    BytesN::from_array(env, &arr)
}

// ---------------------------------------------------------------------------
// constructor
// ---------------------------------------------------------------------------

#[test]
fn test_constructor_sets_state() {
    let ctx = setup();
    let client = ctx.client();

    assert_eq!(client.get_admin(), ctx.admin);
    assert_eq!(client.get_auditor(), ctx.auditor);
    assert_eq!(client.get_skill_count(), 0);
    assert_eq!(
        client.get_trust_score_config(),
        TrustScoreConfig {
            desc_weight: 40,
            sandbox_weight: 40,
            reputation_weight: 20,
        }
    );
    assert_eq!(client.query_all_skills(&0, &10).len(), 0);
}

// ---------------------------------------------------------------------------
// register_skill — authorization
// ---------------------------------------------------------------------------

#[test]
fn test_register_skill_requires_owner_auth() {
    let ctx = setup_no_auth();
    let client = ctx.client();
    let attacker = Address::generate(&ctx.env);
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    let h = hash(&ctx.env, 0x01);

    // Only the attacker signed; the call claims to be `owner` -> must fail.
    let res = client
        .mock_auths(&[MockAuth {
            address: &attacker,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "register_skill",
                args: (
                    attacker.clone(),
                    skill_id.clone(),
                    version.clone(),
                    h.clone(),
                )
                    .into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_register_skill(&ctx.owner, &skill_id, &version, &h);

    assert!(res.is_err(), "register_skill must reject a missing owner auth");
    // Nothing was written.
    assert_eq!(client.get_skill_count(), 0);
    assert!(client.lookup_by_hash(&h).is_none());
}

#[test]
fn test_register_skill_auth_tree() {
    let ctx = setup_no_auth();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    let h = hash(&ctx.env, 0x01);

    client
        .mock_auths(&[MockAuth {
            address: &ctx.owner,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "register_skill",
                args: (
                    ctx.owner.clone(),
                    skill_id.clone(),
                    version.clone(),
                    h.clone(),
                )
                    .into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .register_skill(&ctx.owner, &skill_id, &version, &h);

    assert_eq!(
        ctx.env.auths(),
        std::vec![(
            ctx.owner.clone(),
            AuthorizedInvocation {
                function: AuthorizedFunction::Contract((
                    ctx.contract_id.clone(),
                    Symbol::new(&ctx.env, "register_skill"),
                    (
                        ctx.owner.clone(),
                        skill_id.clone(),
                        version.clone(),
                        h.clone()
                    )
                        .into_val(&ctx.env),
                )),
                sub_invocations: std::vec![],
            }
        )]
    );
}

// ---------------------------------------------------------------------------
// register_skill — happy path & invariants
// ---------------------------------------------------------------------------

#[test]
fn test_register_new_skill_and_query() {
    let ctx = setup();
    let client = ctx.client();
    ctx.env.ledger().set_timestamp(1_000);

    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    let h = hash(&ctx.env, 0x01);
    client.register_skill(&ctx.owner, &skill_id, &version, &h);

    let entry = client.query_skill(&skill_id);
    assert_eq!(
        entry,
        SkillEntry {
            skill_id: skill_id.clone(),
            owner: ctx.owner.clone(),
            versions: soroban_sdk::vec![&ctx.env, version.clone()],
            latest_version: version.clone(),
            latest_audited_version: None,
            registered_at: 1_000,
        }
    );
    assert_eq!(client.get_skill_count(), 1);

    let record = client.get_version(&skill_id, &version);
    assert_eq!(record.skill_id, skill_id);
    assert_eq!(record.version, version);
    assert_eq!(record.content_hash, h);
    assert_eq!(record.owner, ctx.owner);
    assert_eq!(record.registered_at, 1_000);
    assert_eq!(record.verdict, AuditVerdict::Unaudited);
    assert_eq!(record.trust_score, 0);
    assert_eq!(record.auditor, None);
    assert_eq!(record.evidence_hash, BytesN::from_array(&ctx.env, &[0u8; 32]));
    assert_eq!(record.audited_at, 0);
    assert!(!client.is_verified(&skill_id, &version));
}

#[test]
fn test_register_second_version_by_owner() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.csv-parser");
    let v1 = sid(&ctx.env, "1.0.0");
    let v2 = sid(&ctx.env, "2.0.0");

    client.register_skill(&ctx.owner, &skill_id, &v1, &hash(&ctx.env, 0x01));
    client.register_skill(&ctx.owner, &skill_id, &v2, &hash(&ctx.env, 0x02));

    let entry = client.query_skill(&skill_id);
    assert_eq!(entry.versions.len(), 2);
    assert_eq!(entry.versions.get(0).unwrap(), v1);
    assert_eq!(entry.versions.get(1).unwrap(), v2);
    assert_eq!(entry.latest_version, v2);
    // one skill_id, two versions -> the skill count must NOT grow
    assert_eq!(client.get_skill_count(), 1);
    assert_eq!(client.get_latest(&skill_id).version, v2);
}

#[test]
fn test_register_version_by_non_owner_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let intruder = Address::generate(&ctx.env);
    let skill_id = sid(&ctx.env, "com.example.csv-parser");

    client.register_skill(
        &ctx.owner,
        &skill_id,
        &sid(&ctx.env, "1.0.0"),
        &hash(&ctx.env, 0x01),
    );

    assert_registry_err!(
        client.try_register_skill(
            &intruder,
            &skill_id,
            &sid(&ctx.env, "2.0.0"),
            &hash(&ctx.env, 0x02),
        ),
        RegistryError::NotAuthorized
    );
    assert_eq!(client.query_skill(&skill_id).versions.len(), 1);
}

#[test]
fn test_duplicate_version_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.csv-parser");
    let v1 = sid(&ctx.env, "1.0.0");

    client.register_skill(&ctx.owner, &skill_id, &v1, &hash(&ctx.env, 0x01));

    // Same version, different content: a version is immutable once published.
    assert_registry_err!(
        client.try_register_skill(&ctx.owner, &skill_id, &v1, &hash(&ctx.env, 0x99)),
        RegistryError::VersionAlreadyExists
    );
    assert_eq!(
        client.get_version(&skill_id, &v1).content_hash,
        hash(&ctx.env, 0x01)
    );
}

#[test]
fn test_duplicate_hash_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let h = hash(&ctx.env, 0x42);
    let skill_a = sid(&ctx.env, "com.example.a");
    let skill_b = sid(&ctx.env, "com.example.b");

    client.register_skill(&ctx.owner, &skill_a, &sid(&ctx.env, "1.0.0"), &h);

    // Same hash under another skill would make lookup_by_hash ambiguous.
    assert_registry_err!(
        client.try_register_skill(&ctx.owner, &skill_b, &sid(&ctx.env, "1.0.0"), &h),
        RegistryError::HashAlreadyRegistered
    );
    // ...and under another version of the same skill.
    assert_registry_err!(
        client.try_register_skill(&ctx.owner, &skill_a, &sid(&ctx.env, "2.0.0"), &h),
        RegistryError::HashAlreadyRegistered
    );
    assert_eq!(client.get_skill_count(), 1);
}

#[test]
fn test_empty_skill_id_rejected() {
    let ctx = setup();
    let client = ctx.client();
    assert_registry_err!(
        client.try_register_skill(
            &ctx.owner,
            &sid(&ctx.env, ""),
            &sid(&ctx.env, "1.0.0"),
            &hash(&ctx.env, 0x01),
        ),
        RegistryError::InvalidInput
    );
}

#[test]
fn test_empty_version_rejected() {
    let ctx = setup();
    let client = ctx.client();
    assert_registry_err!(
        client.try_register_skill(
            &ctx.owner,
            &sid(&ctx.env, "com.example.a"),
            &sid(&ctx.env, ""),
            &hash(&ctx.env, 0x01),
        ),
        RegistryError::InvalidInput
    );
}

// ---------------------------------------------------------------------------
// lookup_by_hash — the core claim of the proposal
// ---------------------------------------------------------------------------

#[test]
fn test_lookup_by_hash_hit() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    let h = hash(&ctx.env, 0x01);

    client.register_skill(&ctx.owner, &skill_id, &version, &h);

    let record = client.lookup_by_hash(&h).expect("hash must resolve");
    assert_eq!(record.skill_id, skill_id);
    assert_eq!(record.version, version);
    assert_eq!(record.content_hash, h);
}

#[test]
fn test_lookup_by_hash_one_byte_flip_miss() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    let h = hash(&ctx.env, 0x01);

    client.register_skill(&ctx.owner, &skill_id, &version, &h);
    client.submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Safe,
        &90,
        &hash(&ctx.env, 0xAA),
    );

    let tampered = flip_one_byte(&ctx.env, &h);
    assert_ne!(tampered, h);
    // One flipped bit -> unknown artifact, NOT the audited badge.
    assert!(client.lookup_by_hash(&tampered).is_none());
    // The pristine hash still resolves to Safe.
    assert_eq!(
        client.lookup_by_hash(&h).unwrap().verdict,
        AuditVerdict::Safe
    );
}

#[test]
fn test_lookup_by_hash_unknown_returns_none() {
    let ctx = setup();
    let client = ctx.client();
    assert!(client.lookup_by_hash(&hash(&ctx.env, 0xEE)).is_none());
}

#[test]
fn test_lookup_by_hash_returns_verdict_after_audit() {
    let ctx = setup();
    let client = ctx.client();
    ctx.env.ledger().set_timestamp(5_000);
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    let h = hash(&ctx.env, 0x01);
    let evidence = hash(&ctx.env, 0xAA);

    client.register_skill(&ctx.owner, &skill_id, &version, &h);
    assert_eq!(
        client.lookup_by_hash(&h).unwrap().verdict,
        AuditVerdict::Unaudited
    );

    client.submit_verdict(&skill_id, &version, &AuditVerdict::Safe, &88, &evidence);

    let record = client.lookup_by_hash(&h).unwrap();
    assert_eq!(record.verdict, AuditVerdict::Safe);
    assert_eq!(record.trust_score, 88);
    assert_eq!(record.auditor, Some(ctx.auditor.clone()));
    assert_eq!(record.evidence_hash, evidence);
    assert_eq!(record.audited_at, 5_000);
    assert!(client.is_verified(&skill_id, &version));
}

#[test]
fn test_rugpull_v2_cannot_inherit_v1_badge() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let v1 = sid(&ctx.env, "1.0.0");
    let v2 = sid(&ctx.env, "2.0.0");
    let h1 = hash(&ctx.env, 0x01);
    let h2 = hash(&ctx.env, 0x02);

    client.register_skill(&ctx.owner, &skill_id, &v1, &h1);
    client.submit_verdict(&skill_id, &v1, &AuditVerdict::Safe, &95, &hash(&ctx.env, 0xAA));

    // The rug pull: a brand new, unaudited v2 published by the same owner.
    client.register_skill(&ctx.owner, &skill_id, &v2, &h2);

    assert_eq!(
        client.lookup_by_hash(&h1).unwrap().verdict,
        AuditVerdict::Safe
    );
    assert_eq!(
        client.lookup_by_hash(&h2).unwrap().verdict,
        AuditVerdict::Unaudited
    );
    assert!(client.is_verified(&skill_id, &v1));
    assert!(!client.is_verified(&skill_id, &v2));

    // The header still points at v1 as the last audited version, and at v2 as the
    // last registered one — no badge leaks across versions.
    let entry = client.query_skill(&skill_id);
    assert_eq!(entry.latest_version, v2);
    assert_eq!(entry.latest_audited_version, Some(v1.clone()));
    assert_eq!(client.get_latest(&skill_id).verdict, AuditVerdict::Unaudited);
}

// ---------------------------------------------------------------------------
// submit_verdict
// ---------------------------------------------------------------------------

#[test]
fn test_submit_verdict_requires_auditor_auth() {
    let ctx = setup_no_auth();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    let h = hash(&ctx.env, 0x01);
    let evidence = hash(&ctx.env, 0xAA);

    client
        .mock_auths(&[MockAuth {
            address: &ctx.owner,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "register_skill",
                args: (
                    ctx.owner.clone(),
                    skill_id.clone(),
                    version.clone(),
                    h.clone(),
                )
                    .into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .register_skill(&ctx.owner, &skill_id, &version, &h);

    // The skill owner is not the auditor.
    let res = client
        .mock_auths(&[MockAuth {
            address: &ctx.owner,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "submit_verdict",
                args: (
                    skill_id.clone(),
                    version.clone(),
                    AuditVerdict::Safe,
                    100u32,
                    evidence.clone(),
                )
                    .into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_submit_verdict(&skill_id, &version, &AuditVerdict::Safe, &100, &evidence);

    assert!(res.is_err(), "submit_verdict must require the auditor's auth");
    assert!(!client.is_verified(&skill_id, &version));
}

#[test]
fn test_submit_verdict_score_above_100_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    client.register_skill(&ctx.owner, &skill_id, &version, &hash(&ctx.env, 0x01));

    // No silent clamping: a bogus score is a hard failure.
    assert_registry_err!(
        client.try_submit_verdict(
            &skill_id,
            &version,
            &AuditVerdict::Safe,
            &101,
            &hash(&ctx.env, 0xAA),
        ),
        RegistryError::InvalidTrustScore
    );
    assert_eq!(
        client.get_version(&skill_id, &version).verdict,
        AuditVerdict::Unaudited
    );

    // The boundary value is accepted.
    client.submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Safe,
        &100,
        &hash(&ctx.env, 0xAA),
    );
    assert_eq!(client.get_version(&skill_id, &version).trust_score, 100);
}

#[test]
fn test_submit_verdict_unaudited_rejected() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    client.register_skill(&ctx.owner, &skill_id, &version, &hash(&ctx.env, 0x01));

    assert_registry_err!(
        client.try_submit_verdict(
            &skill_id,
            &version,
            &AuditVerdict::Unaudited,
            &50,
            &hash(&ctx.env, 0xAA),
        ),
        RegistryError::InvalidVerdict
    );
}

#[test]
fn test_submit_verdict_unknown_skill() {
    let ctx = setup();
    let client = ctx.client();
    assert_registry_err!(
        client.try_submit_verdict(
            &sid(&ctx.env, "no.such.skill"),
            &sid(&ctx.env, "1.0.0"),
            &AuditVerdict::Safe,
            &50,
            &hash(&ctx.env, 0xAA),
        ),
        RegistryError::SkillNotFound
    );
}

#[test]
fn test_submit_verdict_unknown_version() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    client.register_skill(
        &ctx.owner,
        &skill_id,
        &sid(&ctx.env, "1.0.0"),
        &hash(&ctx.env, 0x01),
    );

    assert_registry_err!(
        client.try_submit_verdict(
            &skill_id,
            &sid(&ctx.env, "9.9.9"),
            &AuditVerdict::Safe,
            &50,
            &hash(&ctx.env, 0xAA),
        ),
        RegistryError::VersionNotFound
    );
}

#[test]
fn test_verdict_per_version_independent() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let v1 = sid(&ctx.env, "1.0.0");
    let v2 = sid(&ctx.env, "2.0.0");

    client.register_skill(&ctx.owner, &skill_id, &v1, &hash(&ctx.env, 0x01));
    client.register_skill(&ctx.owner, &skill_id, &v2, &hash(&ctx.env, 0x02));

    client.submit_verdict(&skill_id, &v1, &AuditVerdict::Safe, &92, &hash(&ctx.env, 0xA1));
    client.submit_verdict(
        &skill_id,
        &v2,
        &AuditVerdict::Dangerous,
        &3,
        &hash(&ctx.env, 0xA2),
    );

    let r1 = client.get_version(&skill_id, &v1);
    let r2 = client.get_version(&skill_id, &v2);
    assert_eq!(r1.verdict, AuditVerdict::Safe);
    assert_eq!(r1.trust_score, 92);
    assert_eq!(r2.verdict, AuditVerdict::Dangerous);
    assert_eq!(r2.trust_score, 3);

    let latest = client.get_latest(&skill_id);
    assert_eq!(latest.version, v2);
    assert_eq!(latest.verdict, AuditVerdict::Dangerous);
    assert!(client.is_verified(&skill_id, &v1));
    assert!(!client.is_verified(&skill_id, &v2));
}

#[test]
fn test_warning_verdict_is_not_verified() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.grey-zone");
    let version = sid(&ctx.env, "1.0.0");
    client.register_skill(&ctx.owner, &skill_id, &version, &hash(&ctx.env, 0x07));

    client.submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Warning,
        &55,
        &hash(&ctx.env, 0xA7),
    );
    assert_eq!(
        client.get_version(&skill_id, &version).verdict,
        AuditVerdict::Warning
    );
    assert!(!client.is_verified(&skill_id, &version));
}

#[test]
fn test_poisoned_skill_dangerous_gate() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.evil.token-drainer");
    let version = sid(&ctx.env, "1.0.0");
    let h = hash(&ctx.env, 0xDE);

    client.register_skill(&ctx.owner, &skill_id, &version, &h);
    client.submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Dangerous,
        &0,
        &hash(&ctx.env, 0xFF),
    );

    let record = client.lookup_by_hash(&h).unwrap();
    assert_eq!(record.verdict, AuditVerdict::Dangerous);
    assert_eq!(record.trust_score, 0);
    // Only Safe may mint a VERIFIED badge.
    assert!(!client.is_verified(&skill_id, &version));
}

// ---------------------------------------------------------------------------
// events
// ---------------------------------------------------------------------------

#[test]
fn test_events_skill_registered_and_version_registered() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let v1 = sid(&ctx.env, "1.0.0");
    let v2 = sid(&ctx.env, "2.0.0");
    let h1 = hash(&ctx.env, 0x01);
    let h2 = hash(&ctx.env, 0x02);

    client.register_skill(&ctx.owner, &skill_id, &v1, &h1);
    assert_eq!(
        ctx.env.events().all(),
        std::vec![
            SkillRegistered {
                skill_id: skill_id.clone(),
                owner: ctx.owner.clone(),
            }
            .to_xdr(&ctx.env, &ctx.contract_id),
            VersionRegistered {
                skill_id: skill_id.clone(),
                version: v1.clone(),
                content_hash: h1.clone(),
                owner: ctx.owner.clone(),
            }
            .to_xdr(&ctx.env, &ctx.contract_id),
        ]
    );

    // A second version of a known skill emits VersionRegistered only.
    client.register_skill(&ctx.owner, &skill_id, &v2, &h2);
    assert_eq!(
        ctx.env.events().all(),
        std::vec![VersionRegistered {
            skill_id: skill_id.clone(),
            version: v2.clone(),
            content_hash: h2.clone(),
            owner: ctx.owner.clone(),
        }
        .to_xdr(&ctx.env, &ctx.contract_id)]
    );
}

#[test]
fn test_version_recorded_event() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    let h = hash(&ctx.env, 0x01);

    client.register_skill(&ctx.owner, &skill_id, &version, &h);
    client.submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Safe,
        &90,
        &hash(&ctx.env, 0xAA),
    );

    // First audit: no flip event, just the indexer handoff.
    assert_eq!(
        ctx.env.events().all(),
        std::vec![VersionRecorded {
            skill_id: skill_id.clone(),
            version: version.clone(),
            content_hash: h.clone(),
            verdict: AuditVerdict::Safe,
            trust_score: 90,
            auditor: ctx.auditor.clone(),
        }
        .to_xdr(&ctx.env, &ctx.contract_id)]
    );
}

#[test]
fn test_verdict_flipped_event() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    let h = hash(&ctx.env, 0x01);

    client.register_skill(&ctx.owner, &skill_id, &version, &h);
    client.submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Safe,
        &90,
        &hash(&ctx.env, 0xAA),
    );

    // Re-audit with the same verdict: no flip event.
    client.submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Safe,
        &80,
        &hash(&ctx.env, 0xAB),
    );
    assert_eq!(
        ctx.env.events().all(),
        std::vec![VersionRecorded {
            skill_id: skill_id.clone(),
            version: version.clone(),
            content_hash: h.clone(),
            verdict: AuditVerdict::Safe,
            trust_score: 80,
            auditor: ctx.auditor.clone(),
        }
        .to_xdr(&ctx.env, &ctx.contract_id)]
    );

    // Safe -> Dangerous flips: VerdictFlipped is published before VersionRecorded.
    client.submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Dangerous,
        &10,
        &hash(&ctx.env, 0xAC),
    );
    assert_eq!(
        ctx.env.events().all(),
        std::vec![
            VerdictFlipped {
                skill_id: skill_id.clone(),
                version: version.clone(),
                old_verdict: AuditVerdict::Safe,
                new_verdict: AuditVerdict::Dangerous,
            }
            .to_xdr(&ctx.env, &ctx.contract_id),
            VersionRecorded {
                skill_id: skill_id.clone(),
                version: version.clone(),
                content_hash: h.clone(),
                verdict: AuditVerdict::Dangerous,
                trust_score: 10,
                auditor: ctx.auditor.clone(),
            }
            .to_xdr(&ctx.env, &ctx.contract_id),
        ]
    );
    assert!(!client.is_verified(&skill_id, &version));
}

// ---------------------------------------------------------------------------
// views
// ---------------------------------------------------------------------------

#[test]
fn test_is_verified_unknown_returns_false() {
    let ctx = setup();
    let client = ctx.client();
    // Neither the skill nor the version exists — must not panic.
    assert!(!client.is_verified(&sid(&ctx.env, "no.such.skill"), &sid(&ctx.env, "1.0.0")));

    let skill_id = sid(&ctx.env, "com.example.send-email");
    client.register_skill(
        &ctx.owner,
        &skill_id,
        &sid(&ctx.env, "1.0.0"),
        &hash(&ctx.env, 0x01),
    );
    assert!(!client.is_verified(&skill_id, &sid(&ctx.env, "9.9.9")));
}

#[test]
fn test_get_latest_and_get_version_not_found() {
    let ctx = setup();
    let client = ctx.client();
    let missing = sid(&ctx.env, "no.such.skill");
    let version = sid(&ctx.env, "1.0.0");

    assert_registry_err!(
        client.try_get_latest(&missing),
        RegistryError::SkillNotFound
    );
    assert_registry_err!(
        client.try_get_version(&missing, &version),
        RegistryError::SkillNotFound
    );
    assert_registry_err!(client.try_query_skill(&missing), RegistryError::SkillNotFound);

    let skill_id = sid(&ctx.env, "com.example.send-email");
    client.register_skill(&ctx.owner, &skill_id, &version, &hash(&ctx.env, 0x01));
    assert_registry_err!(
        client.try_get_version(&skill_id, &sid(&ctx.env, "9.9.9")),
        RegistryError::VersionNotFound
    );
}

#[test]
fn test_query_all_skills_paginated() {
    let ctx = setup();
    let client = ctx.client();
    let ids = [
        "com.example.a",
        "com.example.b",
        "com.example.c",
        "com.example.d",
        "com.example.e",
    ];
    for (i, id) in ids.iter().enumerate() {
        client.register_skill(
            &ctx.owner,
            &sid(&ctx.env, id),
            &sid(&ctx.env, "1.0.0"),
            &hash(&ctx.env, i as u8 + 1),
        );
    }
    assert_eq!(client.get_skill_count(), 5);

    let page1 = client.query_all_skills(&0, &3);
    assert_eq!(page1.len(), 3);
    assert_eq!(page1.get(0).unwrap().skill_id, sid(&ctx.env, ids[0]));
    assert_eq!(page1.get(2).unwrap().skill_id, sid(&ctx.env, ids[2]));

    let page2 = client.query_all_skills(&3, &3);
    assert_eq!(page2.len(), 2);
    assert_eq!(page2.get(0).unwrap().skill_id, sid(&ctx.env, ids[3]));

    // Offset beyond the end, and a saturating limit.
    assert_eq!(client.query_all_skills(&10, &3).len(), 0);
    assert_eq!(client.query_all_skills(&0, &u32::MAX).len(), 5);
    assert_eq!(client.query_all_skills(&0, &0).len(), 0);
}

// ---------------------------------------------------------------------------
// admin-only entry points
// ---------------------------------------------------------------------------

#[test]
fn test_set_auditor_admin_only() {
    let ctx = setup_no_auth();
    let client = ctx.client();
    let new_auditor = Address::generate(&ctx.env);
    let intruder = Address::generate(&ctx.env);

    let res = client
        .mock_auths(&[MockAuth {
            address: &intruder,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "set_auditor",
                args: (new_auditor.clone(),).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_set_auditor(&new_auditor);
    assert!(res.is_err(), "set_auditor must require the admin's auth");
    assert_eq!(client.get_auditor(), ctx.auditor);

    client
        .mock_auths(&[MockAuth {
            address: &ctx.admin,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "set_auditor",
                args: (new_auditor.clone(),).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .set_auditor(&new_auditor);
    assert_eq!(client.get_auditor(), new_auditor);
}

#[test]
fn test_new_auditor_can_submit_verdict() {
    let ctx = setup();
    let client = ctx.client();
    let new_auditor = Address::generate(&ctx.env);
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");

    client.register_skill(&ctx.owner, &skill_id, &version, &hash(&ctx.env, 0x01));
    client.set_auditor(&new_auditor);
    client.submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Safe,
        &70,
        &hash(&ctx.env, 0xAA),
    );

    assert_eq!(
        client.get_version(&skill_id, &version).auditor,
        Some(new_auditor)
    );
}

#[test]
fn test_update_trust_score_config_admin_only() {
    let ctx = setup_no_auth();
    let client = ctx.client();
    let intruder = Address::generate(&ctx.env);
    let new_config = TrustScoreConfig {
        desc_weight: 50,
        sandbox_weight: 30,
        reputation_weight: 20,
    };

    let res = client
        .mock_auths(&[MockAuth {
            address: &intruder,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "update_trust_score_config",
                args: (new_config.clone(),).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .try_update_trust_score_config(&new_config);
    assert!(res.is_err(), "config update must require the admin's auth");
    assert_eq!(client.get_trust_score_config().desc_weight, 40);

    client
        .mock_auths(&[MockAuth {
            address: &ctx.admin,
            invoke: &MockAuthInvoke {
                contract: &ctx.contract_id,
                fn_name: "update_trust_score_config",
                args: (new_config.clone(),).into_val(&ctx.env),
                sub_invokes: &[],
            },
        }])
        .update_trust_score_config(&new_config);
    assert_eq!(client.get_trust_score_config(), new_config);
}

// ---------------------------------------------------------------------------
// TTL / state archival
// ---------------------------------------------------------------------------

#[test]
fn test_ttl_extended_on_write() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let v1 = sid(&ctx.env, "1.0.0");
    let v2 = sid(&ctx.env, "2.0.0");
    let h1 = hash(&ctx.env, 0x01);
    let h2 = hash(&ctx.env, 0x02);

    client.register_skill(&ctx.owner, &skill_id, &v1, &h1);

    let skill_key = DataKey::Skill(skill_id.clone());
    let version_key = DataKey::Version(skill_id.clone(), v1.clone());
    let hash_key = DataKey::HashIndex(h1.clone());
    let index_key = DataKey::SkillIndex(0);

    let (skill_ttl, version_ttl, hash_ttl, index_ttl, instance_ttl) =
        ctx.env.as_contract(&ctx.contract_id, || {
            (
                ctx.env.storage().persistent().get_ttl(&skill_key),
                ctx.env.storage().persistent().get_ttl(&version_key),
                ctx.env.storage().persistent().get_ttl(&hash_key),
                ctx.env.storage().persistent().get_ttl(&index_key),
                ctx.env.storage().instance().get_ttl(),
            )
        });

    for ttl in [skill_ttl, version_ttl, hash_ttl, index_ttl, instance_ttl] {
        assert!(ttl >= BUMP_THRESHOLD, "ttl {} below threshold", ttl);
        // extend_ttl(threshold, BUMP_TO) sets the floor at BUMP_TO.
        assert!(ttl >= BUMP_TO - 1, "ttl {} below the bump floor", ttl);
    }

    // Age the ledger past the bump threshold, then write again.
    let start_seq = ctx.env.ledger().sequence();
    ctx.env
        .ledger()
        .set_sequence_number(start_seq + 100 * DAY_IN_LEDGERS);

    let aged_ttl = ctx.env.as_contract(&ctx.contract_id, || {
        ctx.env.storage().persistent().get_ttl(&skill_key)
    });
    assert!(
        aged_ttl < BUMP_THRESHOLD,
        "aged ttl {} should have dropped below the threshold",
        aged_ttl
    );

    client.register_skill(&ctx.owner, &skill_id, &v2, &h2);

    let (bumped_ttl, bumped_instance) = ctx.env.as_contract(&ctx.contract_id, || {
        (
            ctx.env.storage().persistent().get_ttl(&skill_key),
            ctx.env.storage().instance().get_ttl(),
        )
    });
    assert!(
        bumped_ttl > aged_ttl && bumped_ttl >= BUMP_TO - 1,
        "write must re-extend the TTL: {} -> {}",
        aged_ttl,
        bumped_ttl
    );
    assert!(bumped_instance >= BUMP_TO - 1);
}

#[test]
fn test_ttl_extended_on_submit_verdict() {
    let ctx = setup();
    let client = ctx.client();
    let skill_id = sid(&ctx.env, "com.example.send-email");
    let version = sid(&ctx.env, "1.0.0");
    client.register_skill(&ctx.owner, &skill_id, &version, &hash(&ctx.env, 0x01));

    let version_key = DataKey::Version(skill_id.clone(), version.clone());
    let start_seq = ctx.env.ledger().sequence();
    ctx.env
        .ledger()
        .set_sequence_number(start_seq + 100 * DAY_IN_LEDGERS);

    let aged_ttl = ctx.env.as_contract(&ctx.contract_id, || {
        ctx.env.storage().persistent().get_ttl(&version_key)
    });
    assert!(aged_ttl < BUMP_THRESHOLD);

    client.submit_verdict(
        &skill_id,
        &version,
        &AuditVerdict::Safe,
        &90,
        &hash(&ctx.env, 0xAA),
    );

    let bumped_ttl = ctx.env.as_contract(&ctx.contract_id, || {
        ctx.env.storage().persistent().get_ttl(&version_key)
    });
    assert!(bumped_ttl >= BUMP_TO - 1 && bumped_ttl > aged_ttl);
}
