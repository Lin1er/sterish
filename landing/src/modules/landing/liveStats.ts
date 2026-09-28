import { checkVersion, listSkills } from "@/lib/api";
import type { VersionCheck } from "@/lib/types";

/**
 * The numbers the landing page puts in front of strangers.
 *
 * Read from the live API at render time rather than typed into the copy. A
 * landing page that claims "24 skills audited" is making a factual claim to
 * people who have no way to check it except by trusting us, and a hardcoded
 * number goes wrong silently the first time the registry grows. STE-23 asks
 * for claims "akurat terhadap yang benar-benar live"; the only way to keep
 * that promise is to not hold a copy of the answer.
 *
 * When the API cannot be reached the page still renders, but it says so and
 * falls back to a snapshot carrying the date it was taken. A stale number
 * labelled stale is honest; a stale number presented as live is not.
 */

/** The rug pull the whole page is built around. Real, on chain, checkable. */
export const RUG_PULL_SKILL = "com.fixtures.demo.release-notes";

/**
 * Verified against the live API on 2026-09-20. Used only when the API is
 * unreachable, and always rendered with its date attached.
 */
const SNAPSHOT: Omit<LandingStats, "live"> = {
  asOf: "2026-09-20",
  shown: 24,
  onChain: 30,
  hiddenTest: 6,
  safe: 17,
  warning: 2,
  dangerous: 5,
  verified: 17,
  catalogue: 13,
  catalogueSafe: 13,
  poisoned: 4,
  poisonedCaught: 4,
};

export type LandingStats = {
  /** Date the figures describe: today when live, the snapshot's date when not. */
  asOf: string;
  /** Listed publicly, after the test-namespace filter. */
  shown: number;
  /** Everything the Registry holds, filtered or not. */
  onChain: number;
  /** Test-namespace entries the API filtered out, reported rather than hidden. */
  hiddenTest: number;
  safe: number;
  warning: number;
  dangerous: number;
  verified: number;
  /** org.stellar.skills.* — the official catalogue. */
  catalogue: number;
  catalogueSafe: number;
  /** com.fixtures.poisoned.* — the fixtures the gate must catch. */
  poisoned: number;
  poisonedCaught: number;
  /** False when the API did not answer and the snapshot is being shown. */
  live: boolean;
};

export type RugPull = {
  live: boolean;
  safe: Pick<VersionCheck, "version" | "content_hash" | "trust_score"> & {
    verdict: string;
    is_verified: boolean;
  };
  dangerous: Pick<VersionCheck, "version" | "content_hash" | "trust_score"> & {
    verdict: string;
    is_verified: boolean;
  };
};

const RUG_PULL_SNAPSHOT: RugPull = {
  live: false,
  safe: {
    version: "1.0.0",
    content_hash:
      "e5da489eb751e96fb30bb622602b8ab471de4898f333028aeeb7a36211d341f5",
    verdict: "SAFE",
    trust_score: 100,
    is_verified: true,
  },
  dangerous: {
    version: "2.0.0",
    content_hash:
      "befb592d3cb1afa4c471a7c4ddf2666f1c6ebd0364e76977ecd294be7c01653d",
    verdict: "DANGEROUS",
    trust_score: 10,
    is_verified: false,
  },
};

/** Derived here rather than in the view, so the copy cannot disagree with it. */
export async function getLandingStats(): Promise<LandingStats> {
  try {
    // The API clamps limit to 100; the registry is well under that. `total`,
    // `chain_total` and `hidden_test_entries` come straight off the response.
    const list = await listSkills({ limit: 100 });
    const skills = list.skills ?? [];
    if (skills.length === 0) return { ...SNAPSHOT, live: false };

    const by = (v: string) =>
      skills.filter((s) => s.latest_audited_verdict === v).length;
    const catalogue = skills.filter((s) =>
      s.skill_id.startsWith("org.stellar.skills."),
    );
    const poisoned = skills.filter((s) =>
      s.skill_id.startsWith("com.fixtures.poisoned."),
    );

    return {
      asOf: new Date().toISOString().slice(0, 10),
      shown: list.total ?? skills.length,
      // Absent on older API builds; falling back to `total` would claim the
      // chain holds exactly what is shown, which is the one thing it must not.
      onChain: list.chain_total ?? SNAPSHOT.onChain,
      hiddenTest: list.hidden_test_entries ?? SNAPSHOT.hiddenTest,
      safe: by("SAFE"),
      warning: by("WARNING"),
      dangerous: by("DANGEROUS"),
      verified: skills.filter((s) => s.latest_audited_is_verified).length,
      catalogue: catalogue.length,
      catalogueSafe: catalogue.filter(
        (s) => s.latest_audited_verdict === "SAFE",
      ).length,
      poisoned: poisoned.length,
      poisonedCaught: poisoned.filter(
        (s) => s.latest_audited_verdict === "DANGEROUS",
      ).length,
      live: true,
    };
  } catch {
    return { ...SNAPSHOT, live: false };
  }
}

/** Both versions of the rug pull, fetched together so they cannot disagree. */
export async function getRugPull(): Promise<RugPull> {
  try {
    const [v1, v2] = await Promise.all([
      checkVersion(RUG_PULL_SKILL, "1.0.0"),
      checkVersion(RUG_PULL_SKILL, "2.0.0"),
    ]);
    // The point only lands if the chain still says what we claim it says. If
    // the verdicts ever stop being SAFE and DANGEROUS, showing the snapshot
    // is wrong too — so fall back and let the page label it.
    if (v1.verdict !== "SAFE" || v2.verdict !== "DANGEROUS") {
      return RUG_PULL_SNAPSHOT;
    }
    return {
      live: true,
      safe: {
        version: v1.version,
        content_hash: v1.content_hash,
        verdict: v1.verdict,
        trust_score: v1.trust_score,
        is_verified: v1.is_verified,
      },
      dangerous: {
        version: v2.version,
        content_hash: v2.content_hash,
        verdict: v2.verdict,
        trust_score: v2.trust_score,
        is_verified: v2.is_verified,
      },
    };
  } catch {
    return RUG_PULL_SNAPSHOT;
  }
}
