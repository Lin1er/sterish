import { beforeEach, describe, expect, it } from "vitest";

import { contentHash } from "./contentHash";
import {
  FIXTURE_ARTIFACTS,
  FIXTURE_PAYMENT_TERMS,
  FIXTURE_VERSIONS,
} from "./fixtures";
import { handleMockRequest, resetMockLicences } from "./mockApi";

/**
 * The paid path of the mock (spec 3.7) and the licence read (3.8).
 *
 * These matter more than the read tests, because the UI built on them decides
 * when to ask somebody for money. A mock that served a 200 where the API would
 * challenge, or challenged where the API would refuse, would teach the dashboard
 * to charge for things it should not.
 */

const AGENT = "GBRPYHIL2CI3FNQ4BXLFMNDLFJUNPU2HY3ZMFSHONUCEOASW7QC7OX2H";
const OTHER_AGENT = "GCFCURTZ7XHMTKZRWJ4U2YJ7KXQGJ6V2OQDVZ3YI4XWAHC3C5N4JDNQM";
const SAFE = "com.acme.pdf-suite/0.9.0";

function call(path: string, init: { query?: string; headers?: HeadersInit } = {}) {
  return handleMockRequest(
    new Request(`http://localhost/api/mock/${path}${init.query ?? ""}`, {
      headers: init.headers,
    }),
    path.split("/"),
  );
}

function decode(header: string | null): Record<string, unknown> {
  return JSON.parse(Buffer.from(header ?? "", "base64").toString("utf8"));
}

function paymentFor(overrides: Record<string, unknown> = {}): string {
  return Buffer.from(
    JSON.stringify({
      x402Version: 2,
      payload: { transaction: "AAAA-signed-envelope" },
      accepted: FIXTURE_PAYMENT_TERMS,
      ...overrides,
    }),
  ).toString("base64");
}

beforeEach(() => {
  resetMockLicences();
});

describe("the licensable fixture", () => {
  it("serves bytes whose content hash is the one the registry holds", async () => {
    // The loop the check page closes: buy, save, drop the files back in, get
    // SAFE. It only works if this hash is real, so it is recomputed here.
    const files = Object.entries(FIXTURE_ARTIFACTS["com.acme.pdf-suite@0.9.0"]).map(
      ([path, text]) => ({ path, raw: new TextEncoder().encode(text) }),
    );
    await expect(contentHash(files)).resolves.toBe(
      FIXTURE_VERSIONS["com.acme.pdf-suite@0.9.0"].content_hash,
    );
  });
});

describe("GET /use without a licence", () => {
  it("challenges with a decodable x402 v2 header and an empty body", async () => {
    const response = await call(`use/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": AGENT },
    });
    expect(response.status).toBe(402);
    expect(await response.text()).toBe("{}");

    const challenge = decode(response.headers.get("PAYMENT-REQUIRED"));
    expect(challenge.x402Version).toBe(2);
    expect(challenge.accepts).toEqual([FIXTURE_PAYMENT_TERMS]);
  });

  it("keeps the SAC asset and the payTo account distinct", () => {
    // Spec 3.7 names swapping these as the common stumble.
    expect(FIXTURE_PAYMENT_TERMS.asset).toMatch(/^C[A-Z2-7]{55}$/);
    expect(FIXTURE_PAYMENT_TERMS.payTo).toMatch(/^G[A-Z2-7]{55}$/);
  });
});

describe("GET /use refuses before asking for money", () => {
  it("answers 403 NOT_VERIFIED for a DANGEROUS version", async () => {
    const response = await call("use/com.evil.token-drainer/1.0.0");
    expect(response.status).toBe(403);
    expect(response.headers.get("PAYMENT-REQUIRED")).toBeNull();
    expect((await response.json()).error).toBe("NOT_VERIFIED");
  });

  it("answers 403 for WARNING and UNAUDITED too, not only DANGEROUS", async () => {
    expect((await call("use/com.contrib.csv-cleaner/2.1.0")).status).toBe(403);
    expect((await call("use/com.acme.pdf-suite/0.9.3")).status).toBe(403);
  });

  it("says which part of the name is unknown", async () => {
    const skill = await call("use/com.nope.nothing/1.0.0");
    expect(skill.status).toBe(404);
    expect((await skill.json()).error).toBe("SKILL_NOT_FOUND");

    const version = await call("use/com.acme.pdf-suite/9.9.9");
    expect(version.status).toBe(404);
    expect((await version.json()).error).toBe("VERSION_NOT_FOUND");
  });
});

describe("GET /use with a payment", () => {
  it("mints, serves the artifact, and reports both transactions", async () => {
    const response = await call(`use/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": AGENT, "X-PAYMENT": paymentFor() },
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("X-STERISH-LICENSE")).toBe("minted");
    expect(response.headers.get("X-STERISH-LICENSE-TX")).toMatch(/^[0-9a-z]{64}$/);

    const receipt = decode(response.headers.get("X-PAYMENT-RESPONSE"));
    expect(receipt.success).toBe(true);
    expect(receipt.payer).toBe(AGENT);

    expect(await response.json()).toEqual(
      FIXTURE_ARTIFACTS["com.acme.pdf-suite@0.9.0"],
    );
  });

  it("serves the second request as held, with no payment attached", async () => {
    await call(`use/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": AGENT, "X-PAYMENT": paymentFor() },
    });
    const again = await call(`use/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": AGENT },
    });
    expect(again.status).toBe(200);
    expect(again.headers.get("X-STERISH-LICENSE")).toBe("held");
    expect(again.headers.get("X-STERISH-LICENSE-TX")).toBeNull();
  });

  it("does not charge a holder who sends a payment anyway", async () => {
    await call(`use/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": AGENT, "X-PAYMENT": paymentFor() },
    });
    const twice = await call(`use/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": AGENT, "X-PAYMENT": paymentFor() },
    });
    expect(twice.headers.get("X-STERISH-LICENSE")).toBe("held");
    expect(twice.headers.get("X-PAYMENT-RESPONSE")).toBeNull();
  });

  it("licenses the payer only, not every agent", async () => {
    await call(`use/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": AGENT, "X-PAYMENT": paymentFor() },
    });
    const stranger = await call(`use/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": OTHER_AGENT },
    });
    expect(stranger.status).toBe(402);
  });

  it("rejects a header that is not base64 JSON with 400", async () => {
    const response = await call(`use/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": AGENT, "X-PAYMENT": "not base64 !!" },
    });
    expect(response.status).toBe(400);
    expect((await response.json()).error).toBe("INVALID_PAYMENT");
  });

  it("rejects a payment for different terms with 402 PAYMENT_REJECTED", async () => {
    const response = await call(`use/${SAFE}`, {
      headers: {
        "X-AGENT-ADDRESS": AGENT,
        "X-PAYMENT": paymentFor({
          accepted: { ...FIXTURE_PAYMENT_TERMS, amount: "1" },
        }),
      },
    });
    expect(response.status).toBe(402);
    // A rejection is not a fresh challenge: the client must not read it as
    // "pay again".
    expect(response.headers.get("PAYMENT-REQUIRED")).toBeNull();
    expect((await response.json()).error).toBe("PAYMENT_REJECTED");
  });

  it("refuses to mint when it cannot tell who paid", async () => {
    const response = await call(`use/${SAFE}`, {
      headers: { "X-PAYMENT": paymentFor() },
    });
    expect(response.status).toBe(400);
    expect((await response.json()).error).toBe("UNKNOWN_PAYER");
  });
});

describe("GET /license", () => {
  it("answers held: false before a purchase and true after", async () => {
    const before = await (
      await call(`license/${SAFE}`, { query: `?agent=${AGENT}` })
    ).json();
    expect(before.held).toBe(false);
    expect(before.tokens_contract_id).toMatch(/^C[A-Z2-7]{55}$/);

    await call(`use/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": AGENT, "X-PAYMENT": paymentFor() },
    });

    const after = await (
      await call(`license/${SAFE}`, { query: `?agent=${AGENT}` })
    ).json();
    expect(after.held).toBe(true);
  });

  it("accepts the agent as a header as well as a query parameter", async () => {
    const response = await call(`license/${SAFE}`, {
      headers: { "X-AGENT-ADDRESS": AGENT },
    });
    expect(response.status).toBe(200);
    expect((await response.json()).agent).toBe(AGENT);
  });

  it("answers held: false for a skill that does not exist, as the contract does", async () => {
    const body = await (
      await call("license/com.nope.nothing/1.0.0", { query: `?agent=${AGENT}` })
    ).json();
    expect(body.held).toBe(false);
  });

  it("does not look at the verdict", async () => {
    // A DANGEROUS version still answers the licence question. Hiding holders of
    // a version that flipped is the mistake spec 3.8 was written to avoid.
    const response = await call("license/com.evil.token-drainer/1.0.0", {
      query: `?agent=${AGENT}`,
    });
    expect(response.status).toBe(200);
  });

  it("requires an agent", async () => {
    const response = await call(`license/${SAFE}`);
    expect(response.status).toBe(400);
    expect((await response.json()).error).toBe("MISSING_AGENT");
  });

  it("rejects a contract address as the agent", async () => {
    const response = await call(`license/${SAFE}`, {
      query: `?agent=${FIXTURE_PAYMENT_TERMS.asset}`,
    });
    expect(response.status).toBe(400);
    expect((await response.json()).error).toBe("INVALID_AGENT");
  });
});
