use soroban_sdk::{contracterror, contractevent, contracttype, Address, String};

/// Approximate number of ledgers closed in a day (5s close time).
pub const DAY_IN_LEDGERS: u32 = 17_280;
/// Only extend an entry's TTL when it drops below this many ledgers.
pub const BUMP_THRESHOLD: u32 = 30 * DAY_IN_LEDGERS;
/// TTL floor (in ledgers) every touched entry is bumped to.
pub const BUMP_TO: u32 = 120 * DAY_IN_LEDGERS;

/// Lifecycle of one audit escrow job.
///
/// Stored as the enum itself, not as a `u32` with manual `as u32` casts (the
/// scaffold's approach), so an out-of-range status is unrepresentable and the
/// client SDK sees a real type.
///
/// `Settled` and `Slashed` are both terminal: once a job leaves `Bonded` no
/// further money can move for it.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AuditStatus {
    /// Fee is escrowed, waiting for an auditor to post the agreed bond.
    Open,
    /// Auditor bonded; the audit is in progress. Only state where funds can move.
    Bonded,
    /// Auditor was honest: fee + bond paid out to the auditor. Terminal.
    Settled,
    /// Auditor misbehaved: bond went to the reporter, fee refunded. Terminal.
    Slashed,
}

/// One audit escrow job.
///
/// `skill_id` / `version` link the job to the exact `VersionRecord` in the
/// Registry contract that is being audited — the scaffold had no link at all,
/// so an escrowed job could not be tied to what it paid for.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AuditRequest {
    pub requestor: Address,
    /// `None` until an auditor posts the bond. The scaffold used
    /// `requestor.clone()` as a placeholder, which made "unbonded" and
    /// "self-audited" indistinguishable.
    pub auditor: Option<Address>,
    /// Registry `skill_id` under audit.
    pub skill_id: String,
    /// Registry `version` under audit.
    pub version: String,
    /// USDC pulled from the requestor at create time.
    pub fee_amount: i128,
    /// Bond AGREED at create time. `post_bond` transfers exactly this much, so
    /// an auditor can no longer bond 1 stroop and still collect fee + bond.
    pub bond_amount: i128,
    pub status: AuditStatus,
    pub created_at: u64,
    /// Ledger timestamp of the terminal transition; 0 while `Open` / `Bonded`.
    pub resolved_at: u64,
}

/// Storage keys.
///
/// `UsdcToken` / `Admin` / `NextRequestId` are small and bounded, so they live in
/// instance storage. Jobs grow without bound and live in persistent storage.
///
/// The scaffold kept both `RequestCount` and `NextRequestId`, two counters that
/// could drift apart. Only `NextRequestId` is stored now; the count is derived.
#[contracttype]
#[derive(Clone, Debug)]
pub enum StorageKey {
    /// instance -> Address of the USDC SAC.
    UsdcToken,
    /// instance -> Address allowed to settle / slash.
    Admin,
    /// instance -> u32, the id the next job will get (starts at 1).
    NextRequestId,
    /// persistent: request_id -> AuditRequest
    Request(u32),
}

/// Typed contract errors. The numbers are part of the public ABI — never renumber.
#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum EscrowError {
    /// Instance storage is missing — contract was never constructed.
    NotInitialized = 1,
    RequestNotFound = 2,
    /// `post_bond` on a job that is not `Open`.
    NotOpen = 3,
    /// `settle` / `slash` / `claim_forfeited` on a job that is not `Bonded`.
    NotBonded = 4,
    AlreadySettled = 5,
    AlreadySlashed = 6,
    /// `fee_amount` or `bond_amount` <= 0.
    InvalidAmount = 7,
    /// Empty `skill_id` or `version`.
    InvalidInput = 8,
    /// The requestor tried to audit their own job.
    SelfAudit = 9,
}

/// Emitted when a job is opened and the fee is escrowed.
/// topics: ("request_created", request_id)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RequestCreated {
    #[topic]
    pub request_id: u32,
    pub requestor: Address,
    pub skill_id: String,
    pub fee: i128,
}

/// Emitted when an auditor locks the agreed bond.
/// topics: ("bond_posted", request_id)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BondPosted {
    #[topic]
    pub request_id: u32,
    pub auditor: Address,
    pub bond: i128,
}

/// Emitted when fee + bond are paid out to the auditor.
/// topics: ("settled", request_id)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Settled {
    #[topic]
    pub request_id: u32,
    pub payout: i128,
}

/// Emitted when the bond is redirected to a reporter and the fee refunded.
/// topics: ("slashed", request_id)
#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Slashed {
    #[topic]
    pub request_id: u32,
    pub reporter: Address,
    pub bond: i128,
}
