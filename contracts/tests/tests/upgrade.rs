//! STE-44 — the half of upgradeability that only real wasm can prove.
//!
//! `contracts/{registry,tokens}/src/test.rs` cover the timelock state machine,
//! but they run against contracts registered NATIVELY: there is no wasm to
//! replace, so `update_current_contract_wasm` is never reached. Everything here
//! deploys the artifacts `build.rs` produced and swaps them for real.
//!
//! What each test is actually asking:
//!
//! `test_registry_upgrade_keeps_every_prior_read_and_exposes_the_new_code` —
//! after the swap, does the OLD state read back under the NEW code, through
//! instance keys, payload-carrying persistent keys and tuple values alike; and
//! does a function that did not exist before now answer?
//!
//! `test_the_timelock_is_real_against_a_wasm_that_exists` — the native tests
//! reject `execute_upgrade` with a hash nobody uploaded. Does it still reject
//! when the target is a genuine, uploaded, executable artifact — i.e. is the
//! refusal about the clock, and not about the wasm being fake?
//!
//! `test_upgrading_to_a_wasm_without_an_upgrade_entrypoint_is_terminal` — the
//! trap. Soroban has no built-in guard, so this measures the cost.
//!
//! `test_tokens_upgrade_keeps_the_registry_pointer_and_the_badges` — tokens'
//! `registry` has no setter by design. Does the swap leave it alone?
//!
//! `test_upgrade_then_migrate_needs_two_calls_but_the_upgrader_makes_it_one` —
//! the new implementation only takes effect after the current invocation ends,
//! so a contract cannot upgrade itself and then call its own new migration in
//! the same call. Both halves of that are asserted.

use soroban_sdk::{
    contractclient,
    testutils::{Address as _, Ledger},
    Address, BytesN, Env, IntoVal, String, Val, Vec,
};
use sterish_registry::{AuditVerdict, PendingUpgrade, SkillRegistryClient};
use sterish_tokens::SterishTokensClient;

/// The artifacts `build.rs` compiled for `wasm32v1-none`.
const REGISTRY_WASM: &[u8] = include_bytes!(env!("STERISH_REGISTRY_WASM"));
const TOKENS_WASM: &[u8] = include_bytes!(env!("STERISH_TOKENS_WASM"));
/// The escrow is the one contract with no upgrade entrypoint, on purpose. That
/// makes it the honest stand-in for "a replacement that loses upgradeability".
const NO_UPGRADE_WASM: &[u8] = include_bytes!(env!("STERISH_ESCROW_WASM"));
/// The stand-in "v2" — see `contracts/upgrade-probe`.
const PROBE_WASM: &[u8] = include_bytes!(env!("STERISH_UPGRADE_PROBE_WASM"));

/// Upgrade timelock every fixture is deployed with, in seconds. The value
/// testnet runs.
const DELAY: u64 = 300;

/// Caller-side view of `contracts/upgrade-probe`.
///
/// Declared here rather than depending on the crate: `#[contractclient]` gives a
/// client with no implementation attached, so the fixture's native code is never
/// linked into this test binary and never shows up as dead weight in coverage.
/// Same idiom as `RegistryClient` in `contracts/tokens/src/data.rs`.
#[contractclient(name = "ProbeClient")]
pub trait ProbeInterface {
    fn probe_version(env: Env) -> u32;
    fn get_admin(env: Env) -> Address;
    fn get_skill_count(env: Env) -> u32;
    fn get_skill_index(env: Env, index: u32) -> Option<String>;
    fn lookup_hash(env: Env, content_hash: BytesN<32>) -> Option<(String, String)>;
    fn get_migrated_at(env: Env) -> Option<u64>;
    fn migrate(env: Env, migrated_at: u64);
    fn get_pending_upgrade(env: Env) -> Option<PendingUpgrade>;
    fn get_upgrade_delay(env: Env) -> u64;
    fn is_upgradeable(env: Env) -> bool;
}

/// Caller-side view of the `Upgrader` wrapper in the same fixture crate.
#[contractclient(name = "UpgraderClient")]
pub trait UpgraderInterface {
    fn upgrade_and_migrate(
        env: Env,
        contract_address: Address,
        operator: Address,
        migration_args: Vec<Val>,
    );
}

fn sid(env: &Env, s: &str) -> String {
    String::from_str(env, s)
}

fn hash(env: &Env, byte: u8) -> BytesN<32> {
    let mut arr = [0u8; 32];
    arr[0] = byte;
    arr[19] = byte.wrapping_add(31);
    arr[31] = byte;
    BytesN::from_array(env, &arr)
}

/// A registry deployed FROM WASM (not natively), with two skills registered and
/// one of them audited `Safe` — enough state to notice if a swap loses any.
struct Seeded {
    env: Env,
    registry_id: Address,
    admin: Address,
    owner: Address,
    /// content hash of `com.example.alpha@1.0.0`.
    alpha_hash: BytesN<32>,
}

fn seeded_registry() -> Seeded {
    let env = Env::default();
    env.mock_all_auths();
    env.ledger().set_timestamp(1_000);

    let admin = Address::generate(&env);
    let auditor = Address::generate(&env);
    let owner = Address::generate(&env);
    let registry_id = env.register(REGISTRY_WASM, (admin.clone(), auditor.clone(), DELAY));

    let client = SkillRegistryClient::new(&env, &registry_id);
    let alpha_hash = hash(&env, 0x01);
    client.register_skill(
        &owner,
        &sid(&env, "com.example.alpha"),
        &sid(&env, "1.0.0"),
        &alpha_hash,
    );
    client.register_skill(
        &owner,
        &sid(&env, "com.example.beta"),
        &sid(&env, "1.0.0"),
        &hash(&env, 0x02),
    );
    client.submit_verdict(
        &sid(&env, "com.example.alpha"),
        &sid(&env, "1.0.0"),
        &AuditVerdict::Safe,
        &91,
        &hash(&env, 0xAA),
    );

    Seeded {
        env,
        registry_id,
        admin,
        owner,
        alpha_hash,
    }
}

/// Run the whole two-step upgrade of `contract_id` to `wasm`, waiting out the
/// timelock. Returns the hash the wasm was uploaded under.
fn upgrade_to(env: &Env, contract_id: &Address, wasm: &[u8]) -> BytesN<32> {
    let wasm_hash = env.deployer().upload_contract_wasm(wasm);
    let client = SkillRegistryClient::new(env, contract_id);
    let ready_at = client.propose_upgrade(&wasm_hash);
    env.ledger().set_timestamp(ready_at);
    client.execute_upgrade();
    wasm_hash
}

#[test]
fn test_registry_upgrade_keeps_every_prior_read_and_exposes_the_new_code() {
    let w = seeded_registry();
    let before = SkillRegistryClient::new(&w.env, &w.registry_id);

    // Baseline, read through the OLD code.
    assert_eq!(before.get_skill_count(), 2);
    assert_eq!(before.get_admin(), w.admin);
    assert!(before.is_verified(&sid(&w.env, "com.example.alpha"), &sid(&w.env, "1.0.0")));

    upgrade_to(&w.env, &w.registry_id, PROBE_WASM);

    // Read through the NEW code, at the same address.
    let after = ProbeClient::new(&w.env, &w.registry_id);

    // The function that proves the bytes actually changed: it does not exist in
    // sterish_registry.wasm at all.
    assert_eq!(after.probe_version(), 2);

    // Instance keys.
    assert_eq!(after.get_admin(), w.admin);
    assert_eq!(after.get_skill_count(), 2);
    assert_eq!(after.get_upgrade_delay(), DELAY);

    // Persistent key carrying a payload, and a persistent entry whose VALUE is a
    // tuple. Soroban keys a `#[contracttype]` variant by its NAME, so these only
    // read back because the new code spells the variants the same way — which is
    // exactly the append-only rule, observed rather than asserted.
    assert_eq!(
        after.get_skill_index(&0),
        Some(sid(&w.env, "com.example.alpha"))
    );
    assert_eq!(
        after.get_skill_index(&1),
        Some(sid(&w.env, "com.example.beta"))
    );
    assert_eq!(
        after.lookup_hash(&w.alpha_hash),
        Some((sid(&w.env, "com.example.alpha"), sid(&w.env, "1.0.0")))
    );

    // The executed proposal was cleared before the swap, so the incoming code
    // cannot find a stale one and re-run it.
    assert_eq!(after.get_pending_upgrade(), None);
    // And upgradeability came across: the new wasm carries the machinery too.
    assert!(after.is_upgradeable());

    // The field this version ADDED is absent, because the constructor did not
    // re-run. That is the trap; `migrate` is the way out of it.
    assert_eq!(after.get_migrated_at(), None);
    after.migrate(&4_242);
    assert_eq!(after.get_migrated_at(), Some(4_242));
    // A migration that can run twice can be replayed over state it already
    // touched.
    assert!(after.try_migrate(&9_999).is_err());
}

#[test]
fn test_the_timelock_is_real_against_a_wasm_that_exists() {
    // The native tests reject `execute_upgrade` with a hash nobody uploaded, so
    // on their own they leave open the reading that the refusal is about the
    // wasm being fake. Here the target is uploaded, valid and executable, and it
    // is still refused — the refusal is about the clock.
    let w = seeded_registry();
    let client = SkillRegistryClient::new(&w.env, &w.registry_id);
    let wasm_hash = w.env.deployer().upload_contract_wasm(PROBE_WASM);

    let ready_at = client.propose_upgrade(&wasm_hash);
    assert_eq!(ready_at, 1_000 + DELAY);

    w.env.ledger().set_timestamp(ready_at - 1);
    assert!(client.try_execute_upgrade().is_err());
    // Still the registry: the wasm was not swapped.
    assert_eq!(client.get_skill_count(), 2);

    w.env.ledger().set_timestamp(ready_at);
    client.execute_upgrade();
    assert_eq!(ProbeClient::new(&w.env, &w.registry_id).probe_version(), 2);
}

#[test]
fn test_upgrading_to_a_wasm_without_an_upgrade_entrypoint_is_terminal() {
    // Soroban has NO built-in guard for this: nothing on chain can read the
    // exports of a wasm hash before committing to it, so the contract cannot
    // refuse. What this test does is measure the cost precisely, so the guard
    // that DOES exist — scripts/verify-upgrade-target.sh, run in CI before any
    // Sterish wasm is published — has a demonstrated reason to exist rather than
    // an asserted one.
    let w = seeded_registry();
    let client = SkillRegistryClient::new(&w.env, &w.registry_id);

    upgrade_to(&w.env, &w.registry_id, NO_UPGRADE_WASM);

    // The upgrade machinery is simply gone from the deployed bytes. Not
    // "reverts" — absent, so there is nothing to call.
    assert!(client.try_propose_upgrade(&hash(&w.env, 0x7F)).is_err());
    assert!(client.try_execute_upgrade().is_err());
    assert!(client.try_cancel_upgrade().is_err());

    // Irreversibly: the only thing that could restore it is an upgrade.
    let back = w.env.deployer().upload_contract_wasm(REGISTRY_WASM);
    assert!(client.try_propose_upgrade(&back).is_err());
}

#[test]
fn test_tokens_upgrade_keeps_the_registry_pointer_and_the_badges() {
    let w = seeded_registry();
    let auditor = SkillRegistryClient::new(&w.env, &w.registry_id).get_auditor();
    let minter = Address::generate(&w.env);

    let tokens_id = w.env.register(
        TOKENS_WASM,
        (
            w.admin.clone(),
            w.registry_id.clone(),
            auditor.clone(),
            minter.clone(),
            DELAY,
        ),
    );
    let tokens = SterishTokensClient::new(&w.env, &tokens_id);
    let alpha = sid(&w.env, "com.example.alpha");
    let v1 = sid(&w.env, "1.0.0");
    tokens.mint_verified(&alpha, &v1, &w.owner);
    assert_eq!(tokens.total_supply(), 1);

    // Upgrade the tokens contract to a fresh upload of the same bytes. The point
    // is not new behaviour — it is that the swap leaves `registry` exactly where
    // it was. That field has no setter because repointing it would move the
    // `Safe` gate to somebody else's contract, and an upgrade is the one thing
    // that could work around the missing setter.
    let wasm_hash = w.env.deployer().upload_contract_wasm(TOKENS_WASM);
    let ready_at = tokens.propose_upgrade(&wasm_hash);
    w.env.ledger().set_timestamp(ready_at);
    tokens.execute_upgrade();

    assert_eq!(tokens.get_registry(), w.registry_id);
    assert_eq!(tokens.get_admin(), w.admin);
    assert_eq!(tokens.get_auditor_role(), auditor);
    assert_eq!(tokens.get_minter_role(), minter);
    assert_eq!(tokens.get_upgrade_delay(), DELAY);
    assert_eq!(tokens.get_pending_upgrade(), None);

    // The soulbound badge survived, and the live `Safe` gate still works.
    assert!(tokens.is_verified_token(&alpha, &v1));
    assert_eq!(tokens.total_supply(), 1);
    assert_eq!(tokens.get_token(&1).owner, w.owner);
    let agent = Address::generate(&w.env);
    tokens.mint_license(&agent, &alpha, &v1);
    assert!(tokens.has_license(&agent, &alpha, &v1));
}

#[test]
fn test_upgrade_then_migrate_needs_two_calls_but_the_upgrader_makes_it_one() {
    // Half one: separately, the migration is a SECOND transaction. Between the
    // two, the contract is running new code over state the new code considers
    // half-initialised.
    let w = seeded_registry();
    upgrade_to(&w.env, &w.registry_id, PROBE_WASM);
    let probe = ProbeClient::new(&w.env, &w.registry_id);
    assert_eq!(
        probe.get_migrated_at(),
        None,
        "the constructor must not re-run"
    );

    // Half two: an auxiliary contract can do both in one invocation, because
    // from ITS point of view they are two invocations of somebody else. This is
    // the `Upgrader` pattern, and it is the only way to make upgrade+migrate
    // atomic — the contract cannot do it to itself.
    let w2 = seeded_registry();
    let registry = SkillRegistryClient::new(&w2.env, &w2.registry_id);
    let upgrader_id = w2
        .env
        .register(PROBE_WASM, (w2.admin.clone(), w2.admin.clone(), DELAY));
    let upgrader = UpgraderClient::new(&w2.env, &upgrader_id);

    let wasm_hash = w2.env.deployer().upload_contract_wasm(PROBE_WASM);
    let ready_at = registry.propose_upgrade(&wasm_hash);
    w2.env.ledger().set_timestamp(ready_at);

    let args: Vec<Val> = soroban_sdk::vec![&w2.env, 7_777u64.into_val(&w2.env)];
    upgrader.upgrade_and_migrate(&w2.registry_id, &w2.admin, &args);

    let migrated = ProbeClient::new(&w2.env, &w2.registry_id);
    assert_eq!(migrated.probe_version(), 2);
    assert_eq!(migrated.get_migrated_at(), Some(7_777));
    assert_eq!(
        migrated.get_skill_count(),
        2,
        "state survived the atomic path too"
    );
}
