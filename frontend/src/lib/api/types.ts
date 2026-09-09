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

/** The `error` codes enumerated in spec §4. */
export type ApiErrorCode =
  | "INVALID_CONTENT_HASH"
  | "INVALID_PARAMETER"
  | "NOT_FOUND"
  | "SKILL_NOT_FOUND"
  | "VERSION_NOT_FOUND"
  | "RPC_UNAVAILABLE"
  | "NOT_CONFIGURED"
  | "INTERNAL";

/**
 * A skill row plus the one derived question the table actually asks: is the
 * newest version the audited one? Kept out of the wire types above so it stays
 * obvious which fields came from the API and which the client worked out.
 */
export function hasUnauditedLatest(skill: SkillListItem): boolean {
  return skill.latest_audited_version !== skill.latest_version;
}
