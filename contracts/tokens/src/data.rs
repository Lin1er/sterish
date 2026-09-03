use soroban_sdk::{
    contractclient, contracterror, contractevent, contracttype, Address, Env, String,
};

/// Approximate number of ledgers closed in a day (5s close time).
pub const DAY_IN_LEDGERS: u32 = 17_280;
/// Only extend an entry's TTL when it drops below this many ledgers.
pub const BUMP_THRESHOLD: u32 = 30 * DAY_IN_LEDGERS;
/// TTL floor (in ledgers) every touched entry is bumped to.
pub const BUMP_TO: u32 = 120 * DAY_IN_LEDGERS;

/// Minimal view of the `SkillRegistry` ABI, used for the cross-contract Safe gate.
///
/// Only the one function this contract actually calls is declared. Depending on
/// `sterish-registry` for real would link the entire registry implementation into
/// `sterish_tokens.wasm`; `#[contractclient]` gives a caller-side client with no
/// implementation attached. `is_verified` returns a plain `bool`, so nothing from
/// the frozen registry ABI (`VersionRecord`, `AuditVerdict`, ...) has to be
/// duplicated here and there is nothing that can drift.
///
/// Frozen contract (docs/specs/interfaces.md §2.3, R7): `is_verified` is `true`
/// only when THAT exact version carries `AuditVerdict::Safe`; an unknown skill or
/// version is `false`, never a panic.
#[contractclient(name = "RegistryClient")]
pub trait RegistryInterface {
    fn is_verified(env: Env, skill_id: String, version: String) -> bool;
}

/// Which of the two soulbound token classes a record belongs to.
///
/// `Verified` — the audit badge, at most one per `(skill_id, version)`.
/// `License`  — the right to run one skill version, at most one per
///              `(agent, skill_id, version)`.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TokenKind {
    Verified,
    License,
}

/// One minted soulbound token.
///
/// There is deliberately no `transfer`/`approve`/`burn` path anywhere in this
/// contract, so `owner` is written exactly once, at mint time, and is immutable
/// for the life of the token.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TokenRecord {
    pub token_id: u32,
    pub kind: TokenKind,
    pub skill_id: String,
    pub version: String,
    /// Skill owner for `Verified`, the licensed agent for `License`.
    pub owner: Address,
    pub minted_at: u64,
}

/// Storage keys.
///
/// `Admin` / `Registry` / `AuditorRole` / `MinterRole` / `NextTokenId` are small
/// and bounded, so they live in instance storage. Everything that grows per mint
/// (`Token`, `VerifiedOf`, `LicenseOf`) is persistent and TTL-bumped on write:
/// instance storage is capped at 64KB serialized and would eventually brick the
/// contract if minted tokens accumulated there.
#[contracttype]
#[derive(Clone, Debug)]
pub enum DataKey {
    /// instance -> Address
    Admin,
    /// instance -> Address of the SkillRegistry. Immutable: no setter exists,
    /// same policy as the USDC address in the escrow contract. Repointing the
    /// registry would silently repoint the `Safe` gate.
    Registry,
    /// instance -> Address allowed to `mint_verified`.
    AuditorRole,
    /// instance -> Address allowed to `mint_license` (the x402 seller backend).
    MinterRole,
    /// instance -> u32, the id the next token will get (starts at 1).
    NextTokenId,
    /// persistent: token_id -> TokenRecord
    Token(u32),
    /// persistent: (skill_id, version) -> token_id of the VERIFIED badge
    VerifiedOf(String, String),
    /// persistent: (agent, skill_id, version) -> token_id of the license.
    /// Keyed by version on purpose: a new version does NOT inherit the license
    /// bought for the old one (see SYSTEM_DESIGN §3, `VTOK -.gates.-> LTOK`).
    LicenseOf(Address, String, String),
}

/// Typed contract errors. The numbers are part of the public ABI — never renumber.
#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum TokenError {
    /// Instance storage is missing — contract was never constructed.
    NotInitialized = 1,
    TokenNotFound = 2,
    /// A badge already exists for this version, or the agent already holds a
    /// license for it.
    AlreadyMinted = 3,
    /// The registry says this exact version is not `Safe` (that includes
    /// `Unaudited`, `Warning`, `Dangerous`, and skills it has never seen).
    NotSafeVerdict = 4,
    /// A license was requested for a version that has no VERIFIED badge.
    NotVerified = 5,
    /// Empty `skill_id` or `version`.
    InvalidInput = 6,
}

/// Emitted when a VERIFIED badge is minted for one audited-`Safe` version.
/// topics: ("verified_minted", skill_id, version)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VerifiedMinted {
    #[topic]
    pub skill_id: String,
    #[topic]
    pub version: String,
    pub owner: Address,
}

/// Emitted when an agent is granted a license for one verified version.
/// topics: ("license_minted", skill_id, version)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LicenseMinted {
    #[topic]
    pub skill_id: String,
    #[topic]
    pub version: String,
    pub agent: Address,
}
