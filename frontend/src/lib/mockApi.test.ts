import { afterEach, describe, expect, it, vi } from "vitest";

import { handleMockRequest } from "./mockApi";
import { hasUnauditedLatest, type SkillListItem } from "@/lib/types";
import { FIXTURE_SKILL_LIST } from "@/lib/fixtures";

/**
 * The mock is only useful if it behaves like the spec, including when it says
 * no. A mock that is more forgiving than production trains the UI to expect
 * something it will not get.
 */

function call(path: string, query = "") {
  return handleMockRequest(
    new Request(`http://localhost/api/mock/${path}${query}`),
    path.split("/"),
  );
}

describe("the four verdicts", () => {
  it("are all represented, which the live testnet registry is not", () => {
    const verdicts = new Set(
      FIXTURE_SKILL_LIST.skills.map(
        (skill) => skill.latest_audited_verdict ?? "UNAUDITED",
      ),
    );
    expect(verdicts).toEqual(
      new Set(["SAFE", "WARNING", "DANGEROUS", "UNAUDITED"]),
    );
  });
});

describe("GET /skills", () => {
  it("serves the catalogue", async () => {
    const body = await (await call("skills")).json();
    expect(body.skills).toHaveLength(4);
    expect(body.total).toBe(4);
  });

  it("pages from an offset", async () => {
    const body = await (await call("skills", "?start=2&limit=1")).json();
    expect(body.skills).toHaveLength(1);
    expect(body.start).toBe(2);
    expect(body.skills[0].skill_id).toBe("com.contrib.csv-cleaner");
  });

  it("clamps an oversized limit rather than rejecting it, as the API does", async () => {
    const body = await (await call("skills", "?limit=5000")).json();
    expect(body.limit).toBe(100);
  });

  it("rejects a limit that is not a number", async () => {
    const response = await call("skills", "?limit=abc");
    expect(response.status).toBe(400);
    expect((await response.json()).error).toBe("INVALID_PARAMETER");
  });

  it("rejects a negative offset", async () => {
    const response = await call("skills", "?start=-1");
    expect(response.status).toBe(400);
  });
});

describe("GET /check/by-hash", () => {
  const DRAINER =
    "c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0";

  it("resolves registered bytes to their verdict", async () => {
    const body = await (await call(`check/by-hash/${DRAINER}`)).json();
    expect(body.verdict).toBe("DANGEROUS");
    expect(body.is_verified).toBe(false);
  });

  it("carries is_verified false in the 404 body, per spec 3.1", async () => {
    const response = await call(`check/by-hash/${"f".repeat(64)}`);
    expect(response.status).toBe(404);
    const body = await response.json();
    expect(body.error).toBe("NOT_FOUND");
    // A client reading only this field cannot mistake "unknown" for "fine".
    expect(body.is_verified).toBe(false);
  });

  it("rejects uppercase instead of silently normalising it", async () => {
    const response = await call(`check/by-hash/${DRAINER.toUpperCase()}`);
    expect(response.status).toBe(400);
    expect((await response.json()).error).toBe("INVALID_CONTENT_HASH");
  });

  it("rejects a hash of the wrong length", async () => {
    const response = await call(`check/by-hash/${"a".repeat(63)}`);
    expect(response.status).toBe(400);
  });
});

describe("GET /check/{skill}/{version}", () => {
  it("does not let a verdict leak across versions", async () => {
    // 0.9.0 is SAFE. 0.9.3 is a later, unaudited version of the same skill and
    // must not inherit that verdict: this is the scaffold bug STE-5 removed
    // from the contract, checked here so the mock cannot reintroduce it.
    const safe = await (await call("check/com.acme.pdf-suite/0.9.0")).json();
    const newer = await (await call("check/com.acme.pdf-suite/0.9.3")).json();
    expect(safe.verdict).toBe("SAFE");
    expect(newer.verdict).toBe("UNAUDITED");
    expect(newer.is_verified).toBe(false);
    expect(newer.trust_score).toBe(0);
    expect(newer.auditor).toBeNull();
  });

  it("tells an unknown skill apart from an unknown version", async () => {
    const noSkill = await call("check/com.nope/1.0.0");
    const noVersion = await call("check/com.acme.pdf-suite/9.9.9");
    expect((await noSkill.json()).error).toBe("SKILL_NOT_FOUND");
    expect((await noVersion.json()).error).toBe("VERSION_NOT_FOUND");
  });
});

describe("GET /skills/{skill_id}", () => {
  it("warns when the audited version is not the latest one", async () => {
    const body = await (await call("skills/com.acme.pdf-suite")).json();
    expect(body.latest_version).toBe("0.9.3");
    expect(body.latest_audited_version).toBe("0.9.0");
    expect(body.warning).toContain("NOT the audited version");
  });

  it("reports a never-audited skill as null, not as its latest version", async () => {
    const body = await (await call("skills/com.newbie.hello-world")).json();
    expect(body.latest_audited_version).toBeNull();
    expect(body.audited_versions).toEqual([]);
  });

  it("404s an unknown skill", async () => {
    expect((await call("skills/com.nope")).status).toBe(404);
  });
});

describe("the production gate", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  /**
   * The flag is read once at module load, so the module has to be re-imported
   * after the environment changes. Importing a fresh copy is also the honest
   * test: it is exactly what a production server does at boot.
   */
  async function loadHandler() {
    vi.resetModules();
    return (await import("./mockApi")).handleMockRequest;
  }

  it("serves nothing in a production build", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const handle = await loadHandler();
    const response = handle(new Request("http://localhost/api/mock/skills"), [
      "skills",
    ]);
    // A deployed dashboard that can serve fixtures is a dashboard that can
    // show an invented verdict to a real visitor.
    expect(response.status).toBe(404);
    expect((await response.json()).detail).toContain("production");
  });

  it("can still be switched on deliberately, for verifying a prod build", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("STERISH_ENABLE_MOCK", "1");
    const handle = await loadHandler();
    const response = handle(new Request("http://localhost/api/mock/skills"), [
      "skills",
    ]);
    expect(response.status).toBe(200);
  });
});

describe("GET /feed", () => {
  it("serves activity newest first", async () => {
    const body = await (await call("feed")).json();
    expect(body.indexer_enabled).toBe(true);
    expect(body.events.length).toBeGreaterThan(0);
    const times = body.events.map((e: { occurred_at: number }) => e.occurred_at);
    expect([...times].sort((a, b) => b - a)).toEqual(times);
  });

  it("carries verdict_flipped, which live testnet has never produced", async () => {
    // The whole reason these fixtures exist: a version that was audited once
    // and re-audited to a different verdict is the story this product tells,
    // and there is no live example to render it against.
    const body = await (await call("feed")).json();
    const flipped = body.events.filter(
      (e: { event: string }) => e.event === "verdict_flipped",
    );
    expect(flipped).toHaveLength(1);
    expect(flipped[0].verdict).toBe("WARNING");
  });

  it("gives every event a transaction to check", async () => {
    // The feed comes from the index, which the spec is explicit is a cache and
    // never a source of truth. The tx link is what makes a line checkable
    // rather than a claim the dashboard is making.
    const body = await (await call("feed")).json();
    for (const event of body.events) {
      expect(event.tx_hash).toMatch(/^[0-9a-f]{64}$/);
      expect(event.tx_url).toContain(event.tx_hash);
    }
  });

  it("pages with limit and offset", async () => {
    const body = await (await call("feed", "?limit=2&offset=1")).json();
    expect(body.events).toHaveLength(2);
    expect(body.total).toBeGreaterThan(2);
  });

  it("rejects a limit above what the API allows", async () => {
    const response = await call("feed", "?limit=500");
    expect(response.status).toBe(400);
    expect((await response.json()).error).toBe("INVALID_PARAMETER");
  });
});

describe("an unrouted path", () => {
  it("404s rather than answering with something plausible", async () => {
    expect((await call("reports/com.acme.pdf-suite/0.9.0")).status).toBe(404);
  });
});

describe("hasUnauditedLatest", () => {
  const base: SkillListItem = {
    skill_id: "com.example.one",
    owner: "G".repeat(56),
    registered_at: 0,
    version_count: 1,
    latest_version: "1.0.0",
    latest_audited_version: "1.0.0",
    latest_audited_verdict: "SAFE",
    latest_audited_trust_score: 90,
    latest_audited_is_verified: true,
  };

  it("is false when the audited version is the latest", () => {
    expect(hasUnauditedLatest(base)).toBe(false);
  });

  it("is true when a newer version has shipped since the audit", () => {
    expect(hasUnauditedLatest({ ...base, latest_version: "1.1.0" })).toBe(true);
  });

  it("is true when nothing was ever audited", () => {
    expect(
      hasUnauditedLatest({ ...base, latest_audited_version: null }),
    ).toBe(true);
  });
});
