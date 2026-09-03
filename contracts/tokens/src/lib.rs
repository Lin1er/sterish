#![no_std]
//! Sterish soulbound tokens: the VERIFIED audit badge and the per-agent skill
//! license.
//!
//! # Soulbound by absence, not by revert
//!
//! Neither token can move. This is enforced by the *shape of the ABI*, not by a
//! runtime guard: there is no `transfer`, `transfer_from`, `approve`,
//! `allowance`, `set_approval_for_all`, `burn` or `burn_from` anywhere in this
//! contract, so those entrypoints are absent from the built contract spec and a
//! third party can verify it with `stellar contract info interface`.
//! `scripts/verify-soulbound.sh` does exactly that in CI. A reverting override
//! would still export the symbol and would still have to be trusted; an absent
//! function cannot be called at all.
//!
//! # Why not OpenZeppelin (deliberate deviation from the ticket text)
//!
//! The ticket suggested basing this on the OpenZeppelin Stellar non-fungible
//! module. That was evaluated and rejected by Axel for two independent reasons:
//!
//! 1. **SDK incompatibility.** `stellar-tokens` 0.7.2 (the latest OZ release,
//!    2026-06-09) requires `soroban-sdk ^26.1.0`, while this workspace is pinned
//!    to 27.0.6 and that pin is frozen in `docs/specs`. A real `cargo` resolution
//!    pulls in *two* copies of soroban-sdk (26.1.1 and 27.0.6), whose `Env` and
//!    `Address` types are mutually incompatible.
//! 2. **OZ has no soulbound support.** The `non_fungible` module exposes only the
//!    `NonFungibleToken` and `ContractOverrides` traits — nothing non-transferable.
//!    `#[contractimpl]`-ing `NonFungibleToken` would *export* `transfer`,
//!    `transfer_from` and `approve`, which is precisely what this ticket forbids.
//!
//! So the token model is written directly against `soroban-sdk` 27.0.6, in the
//! same style as `contracts/registry` and `contracts/escrow`.
//!
//! # Trust model
//!
//! `mint_verified` is gated on a live cross-contract call to
//! `SkillRegistry::is_verified(skill_id, version)`, which is `true` only for
//! `AuditVerdict::Safe` on that exact version. That is the on-chain enforcement
//! of the project-wide rule that only `Safe` mints VERIFIED. `mint_license` is
//! in turn gated on the badge existing, so a `Dangerous` skill can never be
//! licensed either.

mod data;
mod test;

pub use data::{
    DataKey, LicenseMinted, RegistryClient, RegistryInterface, TokenError, TokenKind, TokenRecord,
    VerifiedMinted,
};
use data::{BUMP_THRESHOLD, BUMP_TO};
use soroban_sdk::{contract, contractimpl, Address, Env, String};

#[contract]
pub struct SterishTokens;

/// Bump the instance entry (admin/registry/roles/counter) on every write.
fn bump_instance(env: &Env) {
    env.storage().instance().extend_ttl(BUMP_THRESHOLD, BUMP_TO);
}

/// Bump one persistent entry. `extend_ttl` is a floor-only no-op when the current
/// TTL already exceeds the threshold, so calling it on every write is safe and
/// cheap. A badge that gets archived would silently un-verify a skill, so every
/// touched key is bumped.
fn bump_persistent(env: &Env, key: &DataKey) {
    env.storage()
        .persistent()
        .extend_ttl(key, BUMP_THRESHOLD, BUMP_TO);
}

/// Reject empty identifiers before anything is written or any cross-contract call
/// is paid for.
fn check_ids(skill_id: &String, version: &String) -> Result<(), TokenError> {
    if skill_id.is_empty() || version.is_empty() {
        return Err(TokenError::InvalidInput);
    }
    Ok(())
}

#[contractimpl]
impl SterishTokens {
    /// Write a freshly minted token and advance the id counter.
    ///
    /// Returns the id that was assigned. The caller is responsible for having
    /// checked authorization, input validity and the "already minted" index.
    fn mint(env: &Env, kind: TokenKind, skill_id: String, version: String, owner: Address) -> u32 {
        let token_id: u32 = env
            .storage()
            .instance()
            .get(&DataKey::NextTokenId)
            .unwrap_or(1u32);

        let record = TokenRecord {
            token_id,
            kind,
            skill_id,
            version,
            owner,
            minted_at: env.ledger().timestamp(),
        };

        let token_key = DataKey::Token(token_id);
        env.storage().persistent().set(&token_key, &record);
        env.storage()
            .instance()
            .set(&DataKey::NextTokenId, &(token_id + 1));

        bump_persistent(env, &token_key);
        bump_instance(env);

        token_id
    }

    /// Constructor — runs atomically at deploy time, so there is no
    /// deploy->initialize window in which a third party could claim admin or
    /// point the contract at a registry of their own.
    ///
    /// `registry` is stored once and has no setter: repointing it would move the
    /// `Safe` gate to an attacker-controlled contract. Same policy as the USDC
    /// address in `contracts/escrow`.
    pub fn __constructor(
        env: Env,
        admin: Address,
        registry: Address,
        auditor: Address,
        minter: Address,
    ) {
        env.storage().instance().set(&DataKey::Admin, &admin);
        env.storage().instance().set(&DataKey::Registry, &registry);
        env.storage()
            .instance()
            .set(&DataKey::AuditorRole, &auditor);
        env.storage().instance().set(&DataKey::MinterRole, &minter);
        env.storage().instance().set(&DataKey::NextTokenId, &1u32);
        bump_instance(&env);
    }

    /// Mint the VERIFIED badge for one audited-`Safe` skill version.
    ///
    /// Authorized by the stored `AuditorRole`, NOT by `owner` — a skill owner
    /// must never be able to badge their own skill.
    ///
    /// The hard gate is the cross-contract call to
    /// `SkillRegistry::is_verified(skill_id, version)`. `Unaudited`, `Warning`,
    /// `Dangerous` and never-registered skills all come back `false` and are all
    /// rejected with `NotSafeVerdict`.
    ///
    /// **PM decision:** `owner` is supplied by the caller instead of being read
    /// back from the registry. Reading it would mean calling `query_skill`, whose
    /// return type is `SkillEntry`; duplicating that struct in this crate would
    /// create a drift risk against an ABI that is already frozen. The auditor role
    /// is trusted to write verdicts into the registry in the first place, so
    /// trusting it to name the owner adds no new trust surface — and the part that
    /// matters, the `Safe` verdict, is still checked on-chain.
    pub fn mint_verified(
        env: Env,
        skill_id: String,
        version: String,
        owner: Address,
    ) -> Result<u32, TokenError> {
        let auditor = Self::get_auditor_role(env.clone())?;
        auditor.require_auth();

        check_ids(&skill_id, &version)?;

        let registry = Self::get_registry(env.clone())?;
        if !RegistryClient::new(&env, &registry).is_verified(&skill_id, &version) {
            return Err(TokenError::NotSafeVerdict);
        }

        let verified_key = DataKey::VerifiedOf(skill_id.clone(), version.clone());
        if env.storage().persistent().has(&verified_key) {
            return Err(TokenError::AlreadyMinted);
        }

        let token_id = Self::mint(
            &env,
            TokenKind::Verified,
            skill_id.clone(),
            version.clone(),
            owner.clone(),
        );

        env.storage().persistent().set(&verified_key, &token_id);
        bump_persistent(&env, &verified_key);

        VerifiedMinted {
            skill_id,
            version,
            owner,
        }
        .publish(&env);

        Ok(token_id)
    }

    /// Mint a license binding one agent to one verified skill version.
    ///
    /// Authorized by the stored `MinterRole` — the x402 seller backend (STE-19),
    /// which mints only after payment settles. The agent does not sign.
    ///
    /// Gated on the VERIFIED badge existing for that exact version, so a skill the
    /// registry called `Dangerous` can never be sold: it has no badge, so
    /// `NotVerified` is returned.
    pub fn mint_license(
        env: Env,
        agent: Address,
        skill_id: String,
        version: String,
    ) -> Result<u32, TokenError> {
        let minter = Self::get_minter_role(env.clone())?;
        minter.require_auth();

        check_ids(&skill_id, &version)?;

        let verified_key = DataKey::VerifiedOf(skill_id.clone(), version.clone());
        if !env.storage().persistent().has(&verified_key) {
            return Err(TokenError::NotVerified);
        }

        let license_key = DataKey::LicenseOf(agent.clone(), skill_id.clone(), version.clone());
        if env.storage().persistent().has(&license_key) {
            return Err(TokenError::AlreadyMinted);
        }

        let token_id = Self::mint(
            &env,
            TokenKind::License,
            skill_id.clone(),
            version.clone(),
            agent.clone(),
        );

        env.storage().persistent().set(&license_key, &token_id);
        bump_persistent(&env, &license_key);
        // The badge is what makes this license valid; keep it alive alongside it.
        bump_persistent(&env, &verified_key);

        LicenseMinted {
            skill_id,
            version,
            agent,
        }
        .publish(&env);

        Ok(token_id)
    }

    /// True only when this agent holds a license for THIS exact version.
    ///
    /// Never panics on unknown input — the x402 seller calls it to choose between
    /// `200` and `402`, so an unknown triple must be a plain `false`.
    pub fn has_license(env: Env, agent: Address, skill_id: String, version: String) -> bool {
        env.storage()
            .persistent()
            .has(&DataKey::LicenseOf(agent, skill_id, version))
    }

    /// True when a VERIFIED badge exists for this exact version. Unknown is
    /// `false`, never a panic.
    pub fn is_verified_token(env: Env, skill_id: String, version: String) -> bool {
        env.storage()
            .persistent()
            .has(&DataKey::VerifiedOf(skill_id, version))
    }

    /// Read the immutable owner of a token.
    pub fn owner_of(env: Env, token_id: u32) -> Result<Address, TokenError> {
        Ok(Self::get_token(env, token_id)?.owner)
    }

    /// Read one full token record.
    pub fn get_token(env: Env, token_id: u32) -> Result<TokenRecord, TokenError> {
        let key = DataKey::Token(token_id);
        let record: TokenRecord = env
            .storage()
            .persistent()
            .get(&key)
            .ok_or(TokenError::TokenNotFound)?;
        Ok(record)
    }

    /// Number of tokens ever minted. Ids start at 1 and nothing can ever be
    /// burned, so this is exact rather than an upper bound.
    pub fn total_supply(env: Env) -> u32 {
        env.storage()
            .instance()
            .get::<DataKey, u32>(&DataKey::NextTokenId)
            .unwrap_or(1u32)
            .saturating_sub(1)
    }

    /// Read the admin address.
    pub fn get_admin(env: Env) -> Result<Address, TokenError> {
        env.storage()
            .instance()
            .get(&DataKey::Admin)
            .ok_or(TokenError::NotInitialized)
    }

    /// Read the SkillRegistry address the `Safe` gate consults. Immutable.
    pub fn get_registry(env: Env) -> Result<Address, TokenError> {
        env.storage()
            .instance()
            .get(&DataKey::Registry)
            .ok_or(TokenError::NotInitialized)
    }

    /// Read the address allowed to mint VERIFIED badges.
    pub fn get_auditor_role(env: Env) -> Result<Address, TokenError> {
        env.storage()
            .instance()
            .get(&DataKey::AuditorRole)
            .ok_or(TokenError::NotInitialized)
    }

    /// Read the address allowed to mint licenses.
    pub fn get_minter_role(env: Env) -> Result<Address, TokenError> {
        env.storage()
            .instance()
            .get(&DataKey::MinterRole)
            .ok_or(TokenError::NotInitialized)
    }

    /// Rotate the auditor role. Admin only.
    pub fn set_auditor_role(env: Env, auditor: Address) -> Result<(), TokenError> {
        let admin = Self::get_admin(env.clone())?;
        admin.require_auth();
        env.storage()
            .instance()
            .set(&DataKey::AuditorRole, &auditor);
        bump_instance(&env);
        Ok(())
    }

    /// Rotate the minter role. Admin only.
    pub fn set_minter_role(env: Env, minter: Address) -> Result<(), TokenError> {
        let admin = Self::get_admin(env.clone())?;
        admin.require_auth();
        env.storage().instance().set(&DataKey::MinterRole, &minter);
        bump_instance(&env);
        Ok(())
    }
}
