import { describe, expect, it } from "vitest";

import { GET } from "./[...path]/route";
import { hasUnauditedLatest, type SkillListItem } from "@/lib/api/types";
import { FIXTURE_SKILL_LIST } from "@/lib/fixtures/registry";

/**
 * The mock is only useful if it behaves like the spec, including when it says
 * no. A mock that is more forgiving than production trains the UI to expect
 * something it will not get.
 */

function call(path: string, query = "") {
  const segments = path.split("/");
  return GET(
    new Request(`http://localhost/api/mock/${path}${query}`),
    // The generated RouteContext type is not available outside a Next build,
    // and the handler only ever awaits params.
    { params: Promise.resolve({ path: segments }) } as never,
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
