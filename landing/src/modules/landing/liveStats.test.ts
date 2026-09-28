import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SkillList, SkillListItem, VersionCheck } from "@/lib/types";

const listSkills = vi.fn();
const checkVersion = vi.fn();

vi.mock("@/lib/api", () => ({
  API_BASE_URL: "https://api.example.test",
  listSkills: (...args: unknown[]) => listSkills(...args),
  checkVersion: (...args: unknown[]) => checkVersion(...args),
}));

const { getLandingStats, getRugPull } = await import("./liveStats");

/**
 * The landing page states these numbers as fact to strangers who cannot check
 * them. Two failures matter more than the rest:
 *
 *   1. Claiming the chain holds only what we chose to show. CLAUDE.md forbids
 *      hiding the test namespaces silently, and the page's honesty rests on
 *      chain_total surviving every path through here — including the one where
 *      the API is too old to send it.
 *   2. Printing a stale number as if it were live. The fallback must always
 *      arrive with live:false so the page can label it.
 */

function skill(over: Partial<SkillListItem> = {}): SkillListItem {
  return {
    skill_id: "com.example.thing",
    owner: "GAAA",
    registered_at: 0,
    version_count: 1,
    latest_version: "1.0.0",
    latest_audited_version: "1.0.0",
    latest_audited_verdict: "SAFE",
    latest_audited_trust_score: 100,
    latest_audited_is_verified: true,
    ...over,
  };
}

function list(skills: SkillListItem[], over: Partial<SkillList> = {}): SkillList {
  return {
    skills,
    total: skills.length,
    start: 0,
    limit: 100,
    chain_total: skills.length,
    hidden_test_entries: 0,
    ...over,
  };
}

const CATALOGUE = Array.from({ length: 13 }, (_, i) =>
  skill({ skill_id: `org.stellar.skills.group.item-${i}` }),
);
const POISONED = Array.from({ length: 4 }, (_, i) =>
  skill({
    skill_id: `com.fixtures.poisoned.bad-${i}`,
    latest_audited_verdict: "DANGEROUS",
    latest_audited_trust_score: 10,
    latest_audited_is_verified: false,
  }),
);

beforeEach(() => {
  listSkills.mockReset();
  checkVersion.mockReset();
});

describe("getLandingStats", () => {
  it("counts the catalogue and the poisoned fixtures separately", async () => {
    listSkills.mockResolvedValue(
      list([...CATALOGUE, ...POISONED], { chain_total: 23, hidden_test_entries: 6 }),
    );
    const s = await getLandingStats();

    expect(s.live).toBe(true);
    expect(s.catalogue).toBe(13);
    expect(s.catalogueSafe).toBe(13);
    expect(s.poisoned).toBe(4);
    expect(s.poisonedCaught).toBe(4);
    expect(s.verified).toBe(13);
    expect(s.safe).toBe(13);
    expect(s.dangerous).toBe(4);
  });

  it("reports the chain total, not the filtered total", async () => {
    // The whole honesty claim: 24 shown of 30 on chain, 6 filtered.
    listSkills.mockResolvedValue(
      list(CATALOGUE, { total: 24, chain_total: 30, hidden_test_entries: 6 }),
    );
    const s = await getLandingStats();
    expect(s.shown).toBe(24);
    expect(s.onChain).toBe(30);
    expect(s.hiddenTest).toBe(6);
    expect(s.onChain).toBeGreaterThan(s.shown);
  });

  it("never claims the chain holds exactly what is shown when the API omits the counts", async () => {
    // An older API build sends no chain_total. Falling back to `total` would
    // silently assert that nothing is filtered, which is the one claim this
    // page must not make by accident.
    const { chain_total, hidden_test_entries, ...older } = list(CATALOGUE, {
      total: 13,
    });
    void chain_total;
    void hidden_test_entries;
    listSkills.mockResolvedValue(older as SkillList);

    const s = await getLandingStats();
    expect(s.onChain).not.toBe(s.shown);
    expect(s.onChain).toBe(30); // the verified snapshot figure
    expect(s.hiddenTest).toBe(6);
  });

  it("falls back, labelled, when the API throws", async () => {
    listSkills.mockRejectedValue(new Error("gateway down"));
    const s = await getLandingStats();
    expect(s.live).toBe(false);
    expect(s.asOf).toBe("2026-09-20");
    expect(s.catalogueSafe).toBe(13);
  });

  it("treats an empty registry as not-live rather than as zeros", async () => {
    // Rendering "0/0 skills audited" because a read came back empty would be a
    // worse lie than showing the dated snapshot.
    listSkills.mockResolvedValue(list([]));
    const s = await getLandingStats();
    expect(s.live).toBe(false);
    expect(s.catalogue).toBe(13);
  });

  it("dates live figures today, not with the snapshot's date", async () => {
    listSkills.mockResolvedValue(list(CATALOGUE));
    const s = await getLandingStats();
    expect(s.asOf).toBe(new Date().toISOString().slice(0, 10));
  });
});

function check(over: Partial<VersionCheck>): VersionCheck {
  return {
    skill_id: "com.fixtures.demo.release-notes",
    version: "1.0.0",
    content_hash: "a".repeat(64),
    verdict: "SAFE",
    trust_score: 100,
    is_verified: true,
    owner: "GAAA",
    auditor: "GBBB",
    registered_at: 0,
    audited_at: 0,
    audited_at_iso: null,
    ...over,
  } as VersionCheck;
}

describe("getRugPull", () => {
  it("passes both versions through when the chain still tells the story", async () => {
    checkVersion.mockImplementation((_id: string, version: string) =>
      Promise.resolve(
        version === "1.0.0"
          ? check({ version: "1.0.0", content_hash: "e5".repeat(32) })
          : check({
              version: "2.0.0",
              content_hash: "be".repeat(32),
              verdict: "DANGEROUS",
              trust_score: 10,
              is_verified: false,
            }),
      ),
    );

    const r = await getRugPull();
    expect(r.live).toBe(true);
    expect(r.safe.is_verified).toBe(true);
    expect(r.dangerous.is_verified).toBe(false);
    // The hashes differing is the entire argument; equal hashes would mean the
    // page is demonstrating nothing.
    expect(r.safe.content_hash).not.toBe(r.dangerous.content_hash);
  });

  it("falls back rather than showing a story the chain no longer tells", async () => {
    // If v2 were ever re-audited to SAFE, rendering it as the rug pull would
    // be a claim about the chain that the chain contradicts.
    checkVersion.mockResolvedValue(check({ verdict: "SAFE" }));
    const r = await getRugPull();
    expect(r.live).toBe(false);
    expect(r.dangerous.verdict).toBe("DANGEROUS");
  });

  it("falls back when either read fails", async () => {
    checkVersion.mockRejectedValue(new Error("timeout"));
    const r = await getRugPull();
    expect(r.live).toBe(false);
    expect(r.safe.verdict).toBe("SAFE");
    expect(r.dangerous.verdict).toBe("DANGEROUS");
  });
});
