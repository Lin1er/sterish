import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, getLicense, requestSkill } from "./api";

/**
 * The client half of the paid path. What is under test is mostly one
 * distinction: which answers mean "you may be asked to pay", which mean "you
 * paid and it failed", and which mean "nobody knows whether you paid". Getting
 * those confused is how a dashboard charges somebody twice.
 */

const AGENT = "GBRPYHIL2CI3FNQ4BXLFMNDLFJUNPU2HY3ZMFSHONUCEOASW7QC7OX2H";

const TERMS = {
  scheme: "exact",
  network: "stellar:testnet",
  amount: "1000000",
  asset: "CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA",
  payTo: "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU",
  maxTimeoutSeconds: 300,
  extra: { areFeesSponsored: true },
};

function b64(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString("base64");
}

function respond(response: Response) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("requestSkill before paying", () => {
  it("returns the decoded challenge on a 402, rather than throwing", async () => {
    respond(
      new Response("{}", {
        status: 402,
        headers: {
          "PAYMENT-REQUIRED": b64({
            x402Version: 2,
            resource: { url: "u", description: "d", mimeType: "m" },
            accepts: [TERMS],
          }),
        },
      }),
    );

    const outcome = await requestSkill("com.acme.pdf-suite", "0.9.0", {
      agent: AGENT,
    });
    expect(outcome.kind).toBe("payment_required");
    if (outcome.kind === "payment_required") {
      expect(outcome.paymentRequired.accepts[0].amount).toBe("1000000");
    }
  });

  it("sends the agent so an existing licence is served without a charge", async () => {
    const spy = respond(
      Response.json({ "SKILL.md": "# x" }, {
        headers: { "X-STERISH-LICENSE": "held" },
      }),
    );

    const outcome = await requestSkill("com.acme.pdf-suite", "0.9.0", {
      agent: AGENT,
    });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toContain("/use/com.acme.pdf-suite/0.9.0");
    expect((init?.headers as Record<string, string>)["X-AGENT-ADDRESS"]).toBe(
      AGENT,
    );
    expect((init?.headers as Record<string, string>)["X-PAYMENT"]).toBeUndefined();
    expect(outcome).toEqual({
      kind: "granted",
      licence: "held",
      mintTx: null,
      settlement: null,
      artifact: { "SKILL.md": "# x" },
    });
  });

  it("names a challenge it cannot read instead of paying against it", async () => {
    respond(
      new Response("{}", {
        status: 402,
        headers: { "PAYMENT-REQUIRED": "not-a-challenge" },
      }),
    );
    const error = (await requestSkill("a", "1", { agent: AGENT }).catch(
      (cause: unknown) => cause,
    )) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("INVALID_CHALLENGE");
  });

  it("throws 403 NOT_VERIFIED for a version that cannot be sold", async () => {
    respond(
      Response.json(
        { error: "NOT_VERIFIED", detail: "x@1 is DANGEROUS" },
        { status: 403 },
      ),
    );
    const error = (await requestSkill("x", "1", { agent: AGENT }).catch(
      (cause: unknown) => cause,
    )) as ApiError;
    expect(error.status).toBe(403);
    expect(error.code).toBe("NOT_VERIFIED");
  });

  it("escapes the skill id and version into the path", async () => {
    const spy = respond(Response.json({}));
    await requestSkill("../health", "1/2", { agent: AGENT });
    expect(String(spy.mock.calls[0][0])).toContain("/use/..%2Fhealth/1%2F2");
  });
});

describe("requestSkill with a payment", () => {
  it("reports a mint with both transactions", async () => {
    const spy = respond(
      Response.json({ "SKILL.md": "# x" }, {
        headers: {
          "X-STERISH-LICENSE": "minted",
          "X-STERISH-LICENSE-TX": "ab".repeat(32),
          "X-PAYMENT-RESPONSE": b64({ success: true, transaction: "cd".repeat(32) }),
        },
      }),
    );

    const outcome = await requestSkill("x", "1", {
      agent: AGENT,
      payment: "signed",
    });

    const headers = spy.mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers["X-PAYMENT"]).toBe("signed");
    expect(outcome).toMatchObject({
      kind: "granted",
      licence: "minted",
      mintTx: "ab".repeat(32),
      settlement: { transaction: "cd".repeat(32) },
    });
  });

  it("throws a refused payment instead of reading it as a fresh challenge", async () => {
    // Even if a server attached terms again, a 402 after paying is a refusal.
    // Treating it as a new challenge would put a second price in front of
    // somebody whose first payment is still in question.
    respond(
      Response.json(
        { error: "PAYMENT_REJECTED", detail: "insufficient balance" },
        { status: 402, headers: { "PAYMENT-REQUIRED": b64({ x402Version: 2, accepts: [TERMS] }) } },
      ),
    );
    const error = (await requestSkill("x", "1", {
      agent: AGENT,
      payment: "signed",
    }).catch((cause: unknown) => cause)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("PAYMENT_REJECTED");
    expect(error.detail).toBe("insufficient balance");
  });

  it("keeps the facilitator outage distinct from a refusal", async () => {
    respond(
      Response.json(
        { error: "FACILITATOR_UNAVAILABLE", detail: "facilitator /verify unreachable" },
        { status: 503 },
      ),
    );
    const error = (await requestSkill("x", "1", {
      agent: AGENT,
      payment: "signed",
    }).catch((cause: unknown) => cause)) as ApiError;
    expect(error.status).toBe(503);
    expect(error.code).toBe("FACILITATOR_UNAVAILABLE");
  });

  it("marks a lost answer after paying as an unknown outcome, not as unreachable", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    const error = (await requestSkill("x", "1", {
      agent: AGENT,
      payment: "signed",
    }).catch((cause: unknown) => cause)) as ApiError;
    expect(error.code).toBe("PAYMENT_OUTCOME_UNKNOWN");
    expect(error.isTransport).toBe(true);
    expect(error.message).toContain("may or may not");
  });

  it("leaves an unpaid transport failure as a plain transport error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    const error = (await requestSkill("x", "1", { agent: AGENT }).catch(
      (cause: unknown) => cause,
    )) as ApiError;
    expect(error.code).toBeNull();
    expect(error.message).toContain("unreachable");
  });
});

describe("getLicense", () => {
  it("asks about one agent and one version", async () => {
    const spy = respond(
      Response.json({ held: true, skill_id: "x", version: "1", agent: AGENT }),
    );
    const status = await getLicense("com.acme.pdf-suite", "0.9.0", AGENT);
    expect(status.held).toBe(true);
    expect(String(spy.mock.calls[0][0])).toContain(
      `/license/com.acme.pdf-suite/0.9.0?agent=${AGENT}`,
    );
  });

  it("throws on a failed chain read rather than answering held: false", async () => {
    respond(
      Response.json(
        { error: "RPC_UNAVAILABLE", detail: "rpc down" },
        { status: 502 },
      ),
    );
    const error = (await getLicense("x", "1", AGENT).catch(
      (cause: unknown) => cause,
    )) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
  });
});
