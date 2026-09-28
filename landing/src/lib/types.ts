/**
 * Only the shapes this page reads.
 *
 * The dashboard's `src/lib/types.ts` is 327 lines covering the whole API:
 * x402 challenges, settlement receipts, licences, the feed. The landing makes
 * two GET requests, so copying all of that across would import a maintenance
 * burden for code this deployment never runs. These are the same field names
 * as the dashboard's, taken from docs/api-spec.md, which is the contract both
 * apps actually depend on.
 */

/** Spec §2. */
export type Verdict = "SAFE" | "WARNING" | "DANGEROUS" | "UNAUDITED";

/** Spec §3.4. */
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
   * default but always reports what it hid — hiding it silently is forbidden,
   * because a reader must never be able to conclude that what is shown is the
   * whole chain. Optional because older API builds omit them, and a consumer
   * that needs them must decide what to do when they are absent rather than
   * treating `total` as the chain total.
   */
  chain_total?: number;
  hidden_test_entries?: number;
}

/** Spec §3.1 and §3.2. */
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
}
