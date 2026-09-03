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

    assert!(
        res.is_err(),
        "register_skill must reject a missing owner auth"
    );
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
    assert_eq!(
        record.evidence_hash,
        BytesN::from_array(&ctx.env, &[0u8; 32])
    );
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
    client.submit_verdict(
        &skill_id,
        &v1,
        &AuditVerdict::Safe,
        &95,
        &hash(&ctx.env, 0xAA),
    );

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
    assert_eq!(
        client.get_latest(&skill_id).verdict,
        AuditVerdict::Unaudited
    );
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

    assert!(
        res.is_err(),
        "submit_verdict must require the auditor's auth"
    );
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

    client.submit_verdict(
        &skill_id,
        &v1,
        &AuditVerdict::Safe,
        &92,
        &hash(&ctx.env, 0xA1),
    );
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
    assert_registry_err!(
        client.try_query_skill(&missing),
        RegistryError::SkillNotFound
    );

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

// ===========================================================================
// STE-10 — canonical `content_hash` v1: Rust side of the cross-language proof.
//
// Normative spec: docs/specs/content-hash.md
// Shared vectors: docs/specs/vectors/content-hash-vectors.json
// Runner:         scripts/verify-content-hash.sh
//
// This module deliberately re-implements the algorithm instead of importing it:
// the whole point is that three independent implementations (Python, TypeScript,
// Rust) agree. The sha256 is computed with `env.crypto().sha256()`, i.e. the same
// host function a deployed Soroban contract would use.
//
// `test_content_hash_v1_cross_language_vectors` prints a machine-readable report
// (`STERISH_HASH <line>`); the runner diffs it against the other two impls.
// ===========================================================================
mod content_hash_v1 {
    use soroban_sdk::{Bytes, Env};
    // `std` is bound by the `extern crate std;` at the top of this test module.
    use super::std::string::String as StdString;
    use super::std::vec::Vec as StdVec;

    /// Domain-separation prefix. 24 bytes, trailing newline included.
    pub const MAGIC: &[u8] = b"sterish-content-hash/v1\n";

    #[derive(Debug, PartialEq, Eq, Clone, Copy)]
    pub enum HashError {
        EmptyFileSet,
        DuplicatePath,
        InvalidPath,
        NotUtf8,
    }

    impl HashError {
        /// Stable, cross-language error name (matches Python `.kind` and TS `ErrorKind`).
        pub fn kind(self) -> &'static str {
            match self {
                HashError::EmptyFileSet => "EmptyFileSet",
                HashError::DuplicatePath => "DuplicatePath",
                HashError::InvalidPath => "InvalidPath",
                HashError::NotUtf8 => "NotUtf8",
            }
        }
    }

    fn u32be(n: usize) -> [u8; 4] {
        assert!(n <= u32::MAX as usize, "value out of u32 range: {}", n);
        (n as u32).to_be_bytes()
    }

    /// Reject anything that is not a clean, relative, POSIX path.
    fn check_path(path_bytes: &[u8]) -> Result<(), HashError> {
        if path_bytes.is_empty() {
            return Err(HashError::InvalidPath);
        }
        let text = core::str::from_utf8(path_bytes).map_err(|_| HashError::InvalidPath)?;
        if text.contains('\\') || text.contains('\0') {
            return Err(HashError::InvalidPath);
        }
        for part in text.split('/') {
            if part.is_empty() || part == "." || part == ".." {
                return Err(HashError::InvalidPath);
            }
        }
        Ok(())
    }

    /// (a) every CRLF -> LF, (b) every remaining CR -> LF, (c) strip ALL trailing LF.
    /// Written as three literal passes so it maps 1:1 onto the spec text.
    fn normalize_content(raw: &[u8]) -> Result<StdVec<u8>, HashError> {
        core::str::from_utf8(raw).map_err(|_| HashError::NotUtf8)?;

        const CR: u8 = 0x0d;
        const LF: u8 = 0x0a;

        // (a) CRLF -> LF (leftmost, non-overlapping).
        let mut out: StdVec<u8> = StdVec::with_capacity(raw.len());
        let mut i = 0usize;
        while i < raw.len() {
            if raw[i] == CR && i + 1 < raw.len() && raw[i + 1] == LF {
                out.push(LF);
                i += 2;
            } else {
                out.push(raw[i]);
                i += 1;
            }
        }
        // (b) remaining CR -> LF.
        for byte in out.iter_mut() {
            if *byte == CR {
                *byte = LF;
            }
        }
        // (c) strip all trailing LF.
        while out.last() == Some(&LF) {
            out.pop();
        }
        Ok(out)
    }

    /// Build CANON from `(path, raw_content)` pairs. Input order is irrelevant.
    pub fn canonical_bytes(files: &[(&str, &[u8])]) -> Result<StdVec<u8>, HashError> {
        if files.is_empty() {
            return Err(HashError::EmptyFileSet);
        }

        let mut items: StdVec<(&[u8], StdVec<u8>)> = StdVec::with_capacity(files.len());
        for (path, raw) in files {
            let path_bytes = path.as_bytes();
            check_path(path_bytes)?;
            if items.iter().any(|(seen, _)| *seen == path_bytes) {
                return Err(HashError::DuplicatePath);
            }
            items.push((path_bytes, normalize_content(raw)?));
        }

        // ASC bytewise on the RAW path bytes: `Ord for [u8]` is exactly that.
        items.sort_by(|a, b| a.0.cmp(b.0));

        let mut buf: StdVec<u8> = StdVec::new();
        buf.extend_from_slice(MAGIC);
        buf.extend_from_slice(&u32be(items.len()));
        for (path_bytes, content) in &items {
            buf.extend_from_slice(&u32be(path_bytes.len()));
            buf.extend_from_slice(path_bytes);
            buf.extend_from_slice(&u32be(content.len()));
            buf.extend_from_slice(content);
        }
        Ok(buf)
    }

    fn hex_lower(bytes: &[u8]) -> StdString {
        const HEX: &[u8; 16] = b"0123456789abcdef";
        let mut out = StdString::with_capacity(bytes.len() * 2);
        for &b in bytes {
            out.push(HEX[(b >> 4) as usize] as char);
            out.push(HEX[(b & 0x0f) as usize] as char);
        }
        out
    }

    /// 64 lowercase hex chars, hashed with the Soroban host's sha256.
    pub fn content_hash(env: &Env, files: &[(&str, &[u8])]) -> Result<StdString, HashError> {
        let canon = canonical_bytes(files)?;
        let digest = env.crypto().sha256(&Bytes::from_slice(env, &canon));
        Ok(hex_lower(&digest.to_array()))
    }
}

use content_hash_v1::{canonical_bytes, content_hash, HashError, MAGIC};

struct HashVector {
    id: &'static str,
    files: &'static [(&'static str, &'static [u8])],
    expected: &'static str,
    equals: &'static [&'static str],
    differs: &'static [&'static str],
}

struct HashErrorCase {
    id: &'static str,
    files: &'static [(&'static str, &'static [u8])],
    expect: &'static str,
}

/// The real poisoned-skill manifest, pulled straight from the fixture so this
/// test cannot silently drift away from the corpus it claims to bind to.
const POISONED_MANIFEST: &[u8] =
    include_bytes!("../../../docs/specs/vectors/fixtures/poisoned_skill/manifest.json");

const V_SINGLE: &[(&str, &[u8])] = &[(
    "SKILL.md",
    b"# Example Skill\n\nDoes nothing harmful.\nEnd.\n",
)];
const V_POISONED: &[(&str, &[u8])] = &[("manifest.json", POISONED_MANIFEST)];
const V_MULTI: &[(&str, &[u8])] = &[
    ("tools/zeta.py", "# zeta\nprint(\"ζ\")\n".as_bytes()),
    (
        "SKILL.md",
        "# Multi\n\nBerisi karakter non-ASCII: café, 日本語, 🚀\n".as_bytes(),
    ),
    ("assets/data.json", "{\"k\": \"välue\"}\n".as_bytes()),
];
const V_NON_BMP: &[(&str, &[u8])] = &[("😀.md", b"emoji\n"), ("Ａ.md", b"fullwidth\n")];
const V_CRLF: &[(&str, &[u8])] = &[(
    "SKILL.md",
    b"# Example Skill\r\n\r\nDoes nothing harmful.\rEnd.\r\n\r\n\r\n",
)];
const V_FLIP: &[(&str, &[u8])] = &[(
    "SKILL.md",
    b"# Example Skill\n\nDoes nothing harmfuL.\nEnd.\n",
)];
const V_CONCAT_A: &[(&str, &[u8])] = &[("a", b"bc")];
const V_CONCAT_B: &[(&str, &[u8])] = &[("ab", b"c")];

/// Same set, same expected hashes, same order as
/// `docs/specs/vectors/content-hash-vectors.json`.
const HASH_VECTORS: &[HashVector] = &[
    HashVector {
        id: "single-file",
        files: V_SINGLE,
        expected: "eaaad94080f641183a4caa2c03e9ccea36c2d466d446909b5b55e0824d3d9edd",
        equals: &[],
        differs: &[],
    },
    HashVector {
        id: "poisoned-token-drainer",
        files: V_POISONED,
        expected: "c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0",
        equals: &[],
        differs: &[],
    },
    HashVector {
        id: "multi-file-ordering",
        files: V_MULTI,
        expected: "e650ee53b67bf159ff2d64a444d52ed6e76d7f6f6c79869a20864cd8b6c2ade6",
        equals: &[],
        differs: &[],
    },
    HashVector {
        id: "non-bmp-path-order",
        files: V_NON_BMP,
        expected: "3b0f76b5277c35d985428b0603df31b174f04b116a35b511eb47129b6cf78248",
        equals: &[],
        differs: &[],
    },
    HashVector {
        id: "crlf-equals-lf",
        files: V_CRLF,
        expected: "eaaad94080f641183a4caa2c03e9ccea36c2d466d446909b5b55e0824d3d9edd",
        equals: &["single-file"],
        differs: &[],
    },
    HashVector {
        id: "one-byte-flip",
        files: V_FLIP,
        expected: "dcf8d82be686c3cf845e7e7d69300683480d6cb45497816a0dcd5afd4f89732b",
        equals: &[],
        differs: &["single-file"],
    },
    HashVector {
        id: "concat-ambiguity-a",
        files: V_CONCAT_A,
        expected: "9e858aa54369f35e3c42d8ba46462943486c497bf9fa08438c55cc760dec5ae3",
        equals: &[],
        differs: &["concat-ambiguity-b"],
    },
    HashVector {
        id: "concat-ambiguity-b",
        files: V_CONCAT_B,
        expected: "666e8c6ece8f6e3aeb2c4e13f9f36c9ccec5517e2a53450ebeb9a5940875de8e",
        equals: &[],
        differs: &["concat-ambiguity-a"],
    },
];

const HASH_ERROR_CASES: &[HashErrorCase] = &[
    HashErrorCase {
        id: "err-empty-set",
        files: &[],
        expect: "EmptyFileSet",
    },
    HashErrorCase {
        id: "err-duplicate-path",
        files: &[("SKILL.md", b"a\n"), ("SKILL.md", b"b\n")],
        expect: "DuplicatePath",
    },
    HashErrorCase {
        id: "err-not-utf8",
        files: &[("blob.bin", b"\xff\xfe\x00\x01")],
        expect: "NotUtf8",
    },
    HashErrorCase {
        id: "err-absolute-path",
        files: &[("/SKILL.md", b"x\n")],
        expect: "InvalidPath",
    },
    HashErrorCase {
        id: "err-dot-prefix",
        files: &[("./SKILL.md", b"x\n")],
        expect: "InvalidPath",
    },
    HashErrorCase {
        id: "err-dotdot",
        files: &[("../SKILL.md", b"x\n")],
        expect: "InvalidPath",
    },
    HashErrorCase {
        id: "err-empty-path",
        files: &[("", b"x\n")],
        expect: "InvalidPath",
    },
    HashErrorCase {
        id: "err-backslash-separator",
        files: &[("tools\\zeta.py", b"x\n")],
        expect: "InvalidPath",
    },
    HashErrorCase {
        id: "err-double-slash",
        files: &[("tools//zeta.py", b"x\n")],
        expect: "InvalidPath",
    },
];

fn hash_of(env: &Env, id: &str) -> std::string::String {
    let vector = HASH_VECTORS
        .iter()
        .find(|v| v.id == id)
        .unwrap_or_else(|| std::panic!("unknown vector id {}", id));
    content_hash(env, vector.files).expect("vector must hash cleanly")
}

/// Emits the shared cross-language report. Run with `-- --nocapture` (that is what
/// `scripts/verify-content-hash.sh` does) to have the lines compared against the
/// Python and TypeScript reference implementations.
#[test]
fn test_content_hash_v1_cross_language_vectors() {
    let env = Env::default();
    let mut report = std::string::String::new();

    for vector in HASH_VECTORS {
        let got = content_hash(&env, vector.files)
            .unwrap_or_else(|e| std::panic!("vector {} errored: {:?}", vector.id, e));
        assert_eq!(
            got, vector.expected,
            "vector {} drifted from the frozen hash",
            vector.id
        );
        report.push_str(&std::format!("STERISH_HASH VECTOR {} {}\n", vector.id, got));
    }

    for vector in HASH_VECTORS {
        let mine = hash_of(&env, vector.id);
        for other in vector.equals {
            let ok = mine == hash_of(&env, other);
            assert!(ok, "{} must equal {}", vector.id, other);
            report.push_str(&std::format!(
                "STERISH_HASH RELATION {} equals {} {}\n",
                vector.id,
                other,
                if ok { "OK" } else { "FAIL" }
            ));
        }
        for other in vector.differs {
            let ok = mine != hash_of(&env, other);
            assert!(ok, "{} must differ from {}", vector.id, other);
            report.push_str(&std::format!(
                "STERISH_HASH RELATION {} differs {} {}\n",
                vector.id,
                other,
                if ok { "OK" } else { "FAIL" }
            ));
        }
    }

    for case in HASH_ERROR_CASES {
        let got = match content_hash(&env, case.files) {
            Ok(_) => "NO_ERROR",
            Err(e) => e.kind(),
        };
        assert_eq!(got, case.expect, "error case {} mismatched", case.id);
        report.push_str(&std::format!("STERISH_HASH ERROR {} {}\n", case.id, got));
    }

    // One atomic write so parallel test threads cannot interleave the report.
    std::print!("{}", report);
}

#[test]
fn test_content_hash_v1_magic_is_24_bytes() {
    assert_eq!(MAGIC.len(), 24);
    assert_eq!(MAGIC, b"sterish-content-hash/v1\n");
    // The canonical prefix must be MAGIC || u32be(file_count).
    let canon = canonical_bytes(V_SINGLE).unwrap();
    assert_eq!(&canon[..24], MAGIC);
    assert_eq!(&canon[24..28], &[0, 0, 0, 1]);
}

#[test]
fn test_content_hash_v1_crlf_normalization_equals_lf() {
    let env = Env::default();
    assert_eq!(
        content_hash(&env, V_CRLF).unwrap(),
        content_hash(&env, V_SINGLE).unwrap(),
        "CRLF, bare CR and extra trailing newlines must normalize away"
    );
}

#[test]
fn test_content_hash_v1_one_byte_flip_changes_hash() {
    let env = Env::default();
    assert_ne!(
        content_hash(&env, V_FLIP).unwrap(),
        content_hash(&env, V_SINGLE).unwrap(),
        "a single flipped byte must change content_hash"
    );
}

#[test]
fn test_content_hash_v1_length_prefix_removes_concat_ambiguity() {
    let env = Env::default();
    // ("a","bc") and ("ab","c") concatenate to the same raw bytes without prefixes.
    assert_ne!(
        content_hash(&env, V_CONCAT_A).unwrap(),
        content_hash(&env, V_CONCAT_B).unwrap()
    );
}

#[test]
fn test_content_hash_v1_input_order_does_not_matter() {
    let env = Env::default();
    let shuffled: &[(&str, &[u8])] = &[V_MULTI[1], V_MULTI[2], V_MULTI[0]];
    assert_eq!(
        content_hash(&env, V_MULTI).unwrap(),
        content_hash(&env, shuffled).unwrap()
    );
}

#[test]
fn test_content_hash_v1_ordering_is_bytewise_not_utf16() {
    // U+FF21 encodes to EF BC A1, U+1F600 to F0 9F 98 80, so bytewise UTF-8 order
    // puts the fullwidth 'Ａ' first. UTF-16 code-unit order (the JS default sort)
    // would put the emoji first because its high surrogate is 0xD83D < 0xFF21.
    let canon = canonical_bytes(V_NON_BMP).unwrap();
    let first_path_start = 24 + 4 + 4;
    let first_path_len = u32::from_be_bytes([canon[28], canon[29], canon[30], canon[31]]) as usize;
    let first_path = &canon[first_path_start..first_path_start + first_path_len];
    assert_eq!(
        core::str::from_utf8(first_path).unwrap(),
        "Ａ.md",
        "canonical order must be UTF-8 bytewise, not UTF-16 code-unit"
    );
}

#[test]
fn test_content_hash_v1_rejects_bad_input() {
    let env = Env::default();
    assert_eq!(content_hash(&env, &[]), Err(HashError::EmptyFileSet));
    assert_eq!(
        content_hash(&env, &[("SKILL.md", b"a"), ("SKILL.md", b"b")]),
        Err(HashError::DuplicatePath)
    );
    assert_eq!(
        content_hash(&env, &[("blob.bin", b"\xff")]),
        Err(HashError::NotUtf8)
    );
    for bad in [
        "/a.md", "./a.md", "../a.md", "", "a\\b.md", "a//b.md", "a/./b.md",
    ] {
        assert_eq!(
            content_hash(&env, &[(bad, b"x")]),
            Err(HashError::InvalidPath),
            "path {:?} must be rejected",
            bad
        );
    }
}
