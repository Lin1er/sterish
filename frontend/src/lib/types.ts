/**
 * TypeScript mirror of `docs/api-spec.md` v1.0.0, frozen at STE-10.
 *
 * Every field name and nullability here is copied from the spec rather than
 * from a sample response, because the spec is the contract James builds to and
 * the thing STE-10 froze. Where the two ever disagree, the spec wins and this
 * file is the bug.
 *
 * The one rule worth restating from spec §1, because it shapes the whole UI:
 * a verdict belongs to a `(skill_id, version)` pair, never to a skill. There is
 * deliberately no `verdict` field on any skill-level type below.
 */

/** Registry `AuditVerdict`, mirrored from the contract enum (spec §3.1). */
export type Verdict = "SAFE" | "WARNING" | "DANGEROUS" | "UNAUDITED";

/**
 * Spec §2. Present on every verdict-bearing response. A verdict without a link
 * to the transaction that wrote it is an unverifiable claim, which is the exact
 * thing Sterish exists to eliminate, so this is never optional.
 */
export interface Evidence {
  registry_contract_id: string;
  contract_url: string;
  /** Null until the indexer has seen the `version_registered` event. */
  registration_tx: string | null;
  registration_tx_url: string | null;
  /** Null while the version is UNAUDITED: nothing wrote a verdict yet. */
  audit_tx: string | null;
  audit_tx_url: string | null;
  /** 64 hex. Null while unaudited (all-zero on chain, served as null). */
  evidence_hash: string | null;
  /** Off-chain and mutable. Spec §5 step 5: check it against evidence_hash. */
  report_uri: string | null;
}

/** Spec §3.1 and §3.2 share one body: a verdict for exactly one version. */
export interface VersionCheck {
  skill_id: string;
  version: string;
  content_hash: string;
  verdict: Verdict;
  /** 0-100. Zero while unaudited. */
  trust_score: number;
  /** True only for SAFE on this exact version. The only install gate. */
  is_verified: boolean;
  owner: string;
  /** Null while unaudited. */
  auditor: string | null;
  registered_at: number;
  audited_at: number | null;
  audited_at_iso: string | null;
  evidence: Evidence;
}

/** One entry of `audited_versions` in spec §3.3. */
export interface AuditedVersion {
  version: string;
  content_hash: string;
  verdict: Verdict;
  trust_score: number;
  is_verified: boolean;
  audited_at: number;
  evidence: Evidence;
}

/** Spec §3.3. Note the absence of a skill-level verdict: that is design rule A1. */
export interface SkillDetail {
  skill_id: string;
  owner: string;
  registered_at: number;
  /** Every registered version, in registration order. */
  versions: string[];
  /** Last registered. Says nothing about audits. */
  latest_version: string;
  /** Last version that received a verdict, or null if none ever did. */
  latest_audited_version: string | null;
  audited_versions: AuditedVersion[];
  /**
   * Set only when latest_version !== latest_audited_version. The API names the
   * confusion out loud, so the UI must show it rather than swallow it.
   */
  warning: string | null;
}

/**
 * One row of spec §3.4. The verdict fields carry the `latest_audited_` prefix
 * on purpose: a bare `verdict` on a list row is what once let a UI badge a
 * skill whose newest version had never been audited.
 */
export interface SkillListItem {
  skill_id: string;
  owner: string;
  registered_at: number;
  version_count: number;
  latest_version: string;
  latest_audited_version: string | null;
  latest_audited_verdict: Verdict | null;
  latest_audited_trust_score: number | null;
  latest_audited_is_verified: boolean | null;
}

/** Spec §3.4. */
export interface SkillList {
  skills: SkillListItem[];
  total: number;
  start: number;
  limit: number;
  /**
   * Chain reality behind the filtered list. The API hides test namespaces by
   * default but always reports what it hid (CLAUDE.md: hiding it silently is
   * forbidden — a reader must never be able to conclude that what is shown is
   * the whole chain). Optional because older API builds omit them, and a
   * consumer that needs them must say what it does when they are absent
   * rather than quietly treating `total` as the chain total.
   */
  chain_total?: number;
  hidden_test_entries?: number;
}

/** Spec §3.5. Returns 503 rather than 200 when the chain is unreachable. */
export interface Health {
  status: string;
  version: string;
  network: string;
  registry_contract_id: string;
  rpc_url: string;
  rpc_reachable: boolean;
  indexer_lag_ledgers: number | null;
  /** Added by STE-19; absent on older API builds. */
  facilitator_reachable?: boolean;
}

/** Spec §4. Every error response shares this shape. */
export interface ApiErrorBody {
  error: string;
  detail: string;
}

/**
 * The `error` codes enumerated in spec §4, plus the paid path (§3.7) and the
 * licence read (§3.8).
 *
 * `LICENSE_MINT_PENDING` is not in the spec yet. STE-42 adds it: settlement
 * succeeded and the mint did not, and the next request from the same payer
 * finishes the mint without charging again. It is listed here so the UI can
 * say that, rather than tell somebody who has paid to pay again.
 *
 * `PAYMENT_OUTCOME_UNKNOWN` and `INVALID_CHALLENGE` are the client's own: the
 * API never sends them. See `requestSkill` in api.ts.
 */
export type ApiErrorCode =
  | "INVALID_CONTENT_HASH"
  | "INVALID_PARAMETER"
  | "NOT_FOUND"
  | "SKILL_NOT_FOUND"
  | "VERSION_NOT_FOUND"
  | "RPC_UNAVAILABLE"
  | "NOT_CONFIGURED"
  | "INTERNAL"
  | "NOT_VERIFIED"
  | "INVALID_PAYMENT"
  | "PAYMENT_REJECTED"
  | "FACILITATOR_UNAVAILABLE"
  | "ARTIFACT_NOT_FOUND"
  | "ARTIFACT_HASH_MISMATCH"
  | "UNKNOWN_PAYER"
  | "LICENSE_MINT_PENDING"
  | "MISSING_AGENT"
  | "INVALID_AGENT"
  | "OWNERSHIP_PROOF_REQUIRED"
  | "INVALID_OWNERSHIP_PROOF"
  | "LICENSE_READ_FAILED"
  | "FACILITATOR_BAD_RESPONSE"
  | "PAYMENT_OUTCOME_UNKNOWN"
  | "INVALID_CHALLENGE";

/**
 * Spec §3.7, the ownership challenge (STE-48).
 *
 * Who holds a licence is public, so the free path asks the caller to sign a
 * single-use message with the address's own key. The signed text is `message`
 * exactly as returned: the server rebuilds it from its own record of the nonce
 * and trusts nothing the client echoes back.
 */
export interface OwnershipChallenge {
  agent: string;
  skill_id: string;
  version: string;
  nonce: string;
  expires_at: number;
  expires_at_iso: string;
  message: string;
  /** Always "SEP-53" today: ed25519 over sha256("Stellar Signed Message:\n" + message). */
  signature_scheme: string;
}

/** One row of spec §3.10. No verdict: that is a separate read against the registry. */
export interface LicenseRecord {
  token_id: number;
  skill_id: string;
  version: string;
  minted_at: number;
  minted_at_iso: string;
  /** Null when the mint is older than the indexer's event window, or not indexed yet. */
  mint_tx: string | null;
  mint_tx_url: string | null;
}

/** Spec §3.10. Read from the tokens contract's own enumeration, not from events. */
export interface LicenseList {
  agent: string;
  licenses: LicenseRecord[];
  total: number;
  start: number;
  limit: number;
  /** What the contract's supply was when this list was built. */
  total_supply: number;
  tokens_contract_id: string;
  contract_url: string;
}

/**
 * Spec §3.8. Whether one agent holds a licence for one exact version.
 *
 * Deliberately says nothing about the verdict: a licence bought while a
 * version was SAFE survives a later flip to DANGEROUS, and the page has to be
 * able to show both facts at once.
 */
export interface LicenseStatus {
  skill_id: string;
  version: string;
  agent: string;
  held: boolean;
  tokens_contract_id: string;
  contract_url: string;
}

/**
 * One entry of `accepts` in an x402 v2 challenge (spec §3.7).
 *
 * `amount` is in the asset's base units: 7 decimals for USDC, so `1000000` is
 * 0.10. `asset` is the SAC contract (`C...`) the payment calls `transfer` on,
 * and `payTo` is the classic account (`G...`) that receives it. The two are
 * different kinds of address and are never derived from one another.
 */
export interface PaymentRequirement {
  scheme: string;
  network: string;
  amount: string;
  asset: string;
  payTo: string;
  maxTimeoutSeconds: number;
  extra: Record<string, unknown>;
}

/** The decoded `PAYMENT-REQUIRED` header of a 402 from `GET /use`. */
export interface PaymentRequired {
  x402Version: number;
  error?: string;
  resource: { url: string; description: string; mimeType: string };
  accepts: PaymentRequirement[];
}

/**
 * The decoded `X-PAYMENT-RESPONSE` header: the facilitator's settlement
 * receipt. Only `transaction` is relied on; the rest is kept as it arrived.
 */
export interface SettlementReceipt {
  success?: boolean;
  transaction?: string;
  network?: string;
  payer?: string;
  [key: string]: unknown;
}

/**
 * What `GET /use` serves on 200: every file of the skill, path to text, after
 * the API has checked the bytes against the content hash on chain.
 */
export type SkillArtifact = Record<string, string>;

/**
 * One indexed registry event. Served by `GET /feed`, newest first.
 *
 * `/feed` is implemented but **not** in the frozen spec: api-spec.md stops at
 * section 3.7 and mentions it only as a row in the implementation-status
 * table. This shape was read from `api/src/sterish_api/models.py::FeedItem` and
 * checked against the live response, so it is the one part of this file that
 * is not backed by a frozen contract. Treat a change here as a real risk.
 *
 * Three event types appear on live testnet: `skill_registered`,
 * `version_registered` and `version_recorded`. A fourth, `verdict_flipped`, is
 * emitted by the contract and indexed, but has never yet occurred.
 */
export interface FeedEvent {
  event: string;
  skill_id: string;
  /** Null on `skill_registered`, which is about the skill, not a version. */
  version: string | null;
  content_hash: string | null;
  /** Only `version_recorded` and `verdict_flipped` carry a verdict. */
  verdict: Verdict | null;
  trust_score: number | null;
  ledger: number;
  tx_hash: string;
  tx_url: string;
  occurred_at: number | null;
  occurred_at_iso: string | null;
}

export interface FeedResponse {
  events: FeedEvent[];
  total: number;
  /** False when the API runs with polling off; the feed is then empty by design. */
  indexer_enabled: boolean;
  last_indexed_ledger: number | null;
}

/**
 * A skill row plus the one derived question the table actually asks: is the
 * newest version the audited one? Kept out of the wire types above so it stays
 * obvious which fields came from the API and which the client worked out.
 */
export function hasUnauditedLatest(skill: SkillListItem): boolean {
  return skill.latest_audited_version !== skill.latest_version;
}
