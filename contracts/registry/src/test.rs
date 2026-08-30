#![cfg(test)]

use crate::{
    data::{AuditVerdict, TrustScoreConfig},
    SkillRegistry, SkillRegistryClient,
};
use soroban_sdk::{
    testutils::{Address as _, Ledger},
    Address, BytesN, Env, String, Vec,
};

fn create_test_env() -> (Env, Address, Address) {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let auditor = Address::generate(&env);
    (env, admin, auditor)
}

fn register_contract(env: &Env) -> Address {
    env.register_contract(None, SkillRegistry)
}

fn make_hash(env: &Env, byte: u8) -> BytesN<32> {
    let mut arr = [0u8; 32];
    arr[0] = byte;
    BytesN::from_array(env, &arr)
}

#[test]
fn test_initialize() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);

    assert_eq!(client.get_auditor(), auditor);

    let config = client.get_trust_score_config();
    assert_eq!(config.desc_weight, 40);
    assert_eq!(config.sandbox_weight, 40);
    assert_eq!(config.reputation_weight, 20);
}

#[test]
#[should_panic(expected = "already initialized")]
fn test_double_initialize_panics() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);
    client.initialize(&admin, &auditor);
}

#[test]
fn test_register_and_query_skill() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);

    let skill_id = String::from_str(&env, "com.example.send-email");
    let version = String::from_str(&env, "1.0.0");
    let content_hash = make_hash(&env, 0x01);

    client.register_skill(&skill_id, &version, &content_hash);

    let entry = client.query_skill(&skill_id);
    assert_eq!(entry.skill_id, skill_id);
    assert_eq!(entry.versions.len(), 1);
    assert_eq!(entry.latest_verdict, AuditVerdict::Unaudited);
    assert_eq!(entry.trust_score, 0);
}

#[test]
fn test_register_multiple_versions() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);

    let skill_id = String::from_str(&env, "com.example.csv-parser");
    let v1 = String::from_str(&env, "1.0.0");
    let v2 = String::from_str(&env, "2.0.0");

    client.register_skill(&skill_id, &v1, &make_hash(&env, 0x01));
    client.register_skill(&skill_id, &v2, &make_hash(&env, 0x02));

    let entry = client.query_skill(&skill_id);
    assert_eq!(entry.versions.len(), 2);
}

#[test]
fn test_submit_verdict() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);

    let skill_id = String::from_str(&env, "com.example.safe-skill");
    let version = String::from_str(&env, "1.0.0");
    client.register_skill(&skill_id, &version, &make_hash(&env, 0x01));

    // Advance ledger so timestamp > 0.
    env.ledger().set_timestamp(12345);

    let evidence = make_hash(&env, 0xAA);
    client.submit_verdict(&skill_id, &AuditVerdict::Safe, &85, &evidence);

    let entry = client.query_skill(&skill_id);
    assert_eq!(entry.latest_verdict, AuditVerdict::Safe);
    assert_eq!(entry.trust_score, 85);
    assert_eq!(entry.auditor, auditor);
    assert_eq!(entry.evidence_hash, evidence);
    assert!(entry.audit_timestamp > 0);
}

#[test]
fn test_submit_verdict_clamps_score() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);

    let skill_id = String::from_str(&env, "com.example.clamped");
    let version = String::from_str(&env, "1.0.0");
    client.register_skill(&skill_id, &version, &make_hash(&env, 0x01));

    client.submit_verdict(&skill_id, &AuditVerdict::Safe, &150, &make_hash(&env, 0xBB));

    let entry = client.query_skill(&skill_id);
    assert_eq!(entry.trust_score, 100);
}

#[test]
#[should_panic(expected = "skill not found")]
fn test_query_nonexistent_skill_panics() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);

    let missing = String::from_str(&env, "no.such.skill");
    client.query_skill(&missing);
}

#[test]
fn test_query_all_skills_paginated() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);

    for i in 0..5u32 {
        let sid = format_u32(&env, "skill.{}", i);
        let ver = String::from_str(&env, "1.0.0");
        client.register_skill(&sid, &ver, &make_hash(&env, i as u8));
    }

    let page1 = client.query_all_skills(&0, &3);
    assert_eq!(page1.len(), 3);

    let page2 = client.query_all_skills(&3, &3);
    assert_eq!(page2.len(), 2);

    let empty = client.query_all_skills(&10, &3);
    assert_eq!(empty.len(), 0);
}

#[test]
fn test_set_auditor() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);
    assert_eq!(client.get_auditor(), auditor);

    let new_auditor = Address::generate(&env);
    client.set_auditor(&new_auditor);
    assert_eq!(client.get_auditor(), new_auditor);
}

#[test]
fn test_update_trust_score_config() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);

    let new_config = TrustScoreConfig {
        desc_weight: 50,
        sandbox_weight: 30,
        reputation_weight: 20,
    };
    client.update_trust_score_config(&new_config);

    let config = client.get_trust_score_config();
    assert_eq!(config.desc_weight, 50);
    assert_eq!(config.sandbox_weight, 30);
}

#[test]
fn test_dangerous_verdict() {
    let (env, admin, auditor) = create_test_env();
    let contract_id = register_contract(&env);
    let client = SkillRegistryClient::new(&env, &contract_id);

    client.initialize(&admin, &auditor);

    let skill_id = String::from_str(&env, "com.evil.drainer");
    let version = String::from_str(&env, "1.0.0");
    client.register_skill(&skill_id, &version, &make_hash(&env, 0xDE));

    client.submit_verdict(&skill_id, &AuditVerdict::Dangerous, &5, &make_hash(&env, 0xFF));

    let entry = client.query_skill(&skill_id);
    assert_eq!(entry.latest_verdict, AuditVerdict::Dangerous);
    assert_eq!(entry.trust_score, 5);
}

/// Helper to format strings in tests (no_std compatible).
mod fmt {
    use soroban_sdk::Env;

    pub fn format(env: &Env, prefix: &str, num: u32) -> soroban_sdk::String {
        // Simple formatting: prefix + number as decimal string
        let mut buf = [0u8; 64];
        let mut idx = 0;
        for &b in prefix.as_bytes() {
            if idx < buf.len() {
                buf[idx] = b;
                idx += 1;
            }
        }
        if num == 0 {
            if idx < buf.len() {
                buf[idx] = b'0';
                idx += 1;
            }
        } else {
            let mut n = num;
            let mut digits = [0u8; 10];
            let mut dlen = 0;
            while n > 0 {
                digits[dlen] = (n % 10) as u8 + b'0';
                n /= 10;
                dlen += 1;
            }
            for &d in digits[..dlen].iter().rev() {
                if idx < buf.len() {
                    buf[idx] = d;
                    idx += 1;
                }
            }
        }
        let s = core::str::from_utf8(&buf[..idx]).unwrap_or("");
        soroban_sdk::String::from_str(env, s)
    }
}

use fmt::format as format_u32;