import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import {
  describeProofFailure,
  isChallengeUsable,
  isValidSignature,
  requestSkillProving,
} from "./ownership";
import type { OwnershipChallenge } from "./types";

/**
 * The ownership proof is what stands between "this wallet holds a licence" and
 * "somebody typed a holder's address". Two things must hold: a 401 asking for a
 * proof is part of the flow and never shown as a failure, and a proof is only
 * ever built from the challenge the API itself pointed at.
 */

const AGENT = "GDUKDRK63Q24NORQ4SQPUQKZNASZELTDXR7TCLV5T6X5X2BYCLEYNITH";
const CHALLENGE_URL =
  "https://api.sterish.xyz/use/org.example.skill/1.0.0/challenge?agent=" +
  AGENT;
const SIGNATURE = Buffer.alloc(64, 7).toString("base64");

const CHALLENGE: OwnershipChallenge = {
  agent: AGENT,
  skill_id: "org.example.skill",
  version: "1.0.0",
  nonce: "a".repeat(32),
  expires_at: Math.floor(Date.now() / 1000) + 300,
  expires_at_iso: "2026-09-24T12:00:00Z",
  message: "Sterish licence ownership proof\nagent: " + AGENT,
  signature_scheme: "SEP-53",
};

vi.mock("./wallet", async () => {
  const actual = await vi.importActual<typeof import("./wallet")>("./wallet");
  return {
    ...actual,
    signMessage: vi.fn(async () => SIGNATURE),
    NETWORK_PASSPHRASE: "Test SDF Network ; September 2015",
  };
});

afterEach(() => {
  vi.restoreAllMocks();
});

function proofRequired(): Response {
  return Response.json(
    {
      error: "OWNERSHIP_PROOF_REQUIRED",
      detail: "prove you control it",
      challenge_url: CHALLENGE_URL,
    },
    { status: 401 },
  );
}

describe("isValidSignature", () => {
  it("accepts 64 bytes of base64, the SEP-53 shape", () => {
    expect(isValidSignature(SIGNATURE)).toBe(true);
  });

  it("refuses anything else, rather than sending it and being told no", () => {
    expect(isValidSignature(Buffer.alloc(32).toString("base64"))).toBe(false);
    expect(isValidSignature("not base64 !!")).toBe(false);
    expect(isValidSignature("")).toBe(false);
  });
});

describe("isChallengeUsable", () => {
  const at = (expires: number) => ({ ...CHALLENGE, expires_at: expires });

  it("is true while there is time to sign", () => {
    expect(isChallengeUsable(at(1000), 700)).toBe(true);
  });

  it("is false once it has expired or is about to", () => {
    expect(isChallengeUsable(at(1000), 1001)).toBe(false);
    expect(isChallengeUsable(at(1000), 998)).toBe(false);
  });
});

describe("requestSkillProving", () => {
  it("serves a skill with no proof when the API does not ask for one", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        Response.json({ "SKILL.md": "# x" }, {
          headers: { "X-STERISH-LICENSE": "held" },
        }),
      );

    const outcome = await requestSkillProving("org.example.skill", "1.0.0", {
      agent: AGENT,
    });
    expect(outcome.kind).toBe("granted");
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("fetches the challenge the 401 named, signs it, and repeats the request", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(proofRequired())
      .mockResolvedValueOnce(Response.json(CHALLENGE))
      .mockResolvedValueOnce(
        Response.json({ "SKILL.md": "# x" }, {
          headers: { "X-STERISH-LICENSE": "held" },
        }),
      );

    const proving = vi.fn();
    const outcome = await requestSkillProving("org.example.skill", "1.0.0", {
      agent: AGENT,
      onProving: proving,
    });

    expect(outcome.kind).toBe("granted");
    expect(proving).toHaveBeenCalledOnce();
    // The challenge URL is taken from the body, never built by the client.
    expect(String(spy.mock.calls[1][0])).toBe(CHALLENGE_URL);
    const headers = spy.mock.calls[2][1]?.headers as Record<string, string>;
    expect(headers["X-STERISH-PROOF-NONCE"]).toBe(CHALLENGE.nonce);
    expect(headers["X-STERISH-PROOF-SIGNATURE"]).toBe(SIGNATURE);
    expect(headers["X-AGENT-ADDRESS"]).toBe(AGENT);
  });

  it("refuses a challenge issued for another address", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(proofRequired())
      .mockResolvedValueOnce(
        Response.json({ ...CHALLENGE, agent: "G" + "B".repeat(55) }),
      );

    await expect(
      requestSkillProving("org.example.skill", "1.0.0", { agent: AGENT }),
    ).rejects.toThrow("not for the connected wallet");
  });

  it("refuses a scheme it does not sign", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(proofRequired())
      .mockResolvedValueOnce(
        Response.json({ ...CHALLENGE, signature_scheme: "SEP-99" }),
      );

    await expect(
      requestSkillProving("org.example.skill", "1.0.0", { agent: AGENT }),
    ).rejects.toThrow("SEP-99");
  });

  it("passes a 402 challenge through untouched, so paying still works", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", {
        status: 402,
        headers: {
          "PAYMENT-REQUIRED": Buffer.from(
            JSON.stringify({
              x402Version: 2,
              accepts: [
                {
                  scheme: "exact",
                  network: "stellar:testnet",
                  amount: "1000000",
                  asset: "CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA",
                  payTo: "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU",
                },
              ],
            }),
          ).toString("base64"),
        },
      }),
    );

    const outcome = await requestSkillProving("org.example.skill", "1.0.0", {
      agent: AGENT,
    });
    expect(outcome.kind).toBe("payment_required");
  });

  it("does not try to prove an error that is not about proof", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        Response.json(
          { error: "NOT_VERIFIED", detail: "x@1 is DANGEROUS" },
          { status: 403 },
        ),
      );

    await expect(
      requestSkillProving("org.example.skill", "1.0.0", { agent: AGENT }),
    ).rejects.toMatchObject({ code: "NOT_VERIFIED" });
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("describeProofFailure", () => {
  it("tells a refused proof apart, and says a fresh one is needed", () => {
    const failure = describeProofFailure(
      new ApiError({
        message: "nonce already used",
        status: 401,
        code: "INVALID_OWNERSHIP_PROOF",
        detail: "nonce already used",
        url: "https://api.sterish.xyz/use/x/1",
      }),
    );
    expect(failure.kind).toBe("expired");
    expect(failure.message).toContain("single use");
  });

  it("reads a declined signature as a decision, not a failure", () => {
    const failure = describeProofFailure(
      new Error("The user rejected this request."),
    );
    expect(failure.kind).toBe("declined");
    // Nobody should think they were charged for refusing to sign.
    expect(failure.message).toContain("not a payment");
  });

  it("names a missing wallet as such", () => {
    expect(
      describeProofFailure(new Error("Freighter is not connected")).kind,
    ).toBe("wallet_unavailable");
  });

  it("reads a wallet's own rejection object, not [object Object]", () => {
    // The kit rejects with a plain object; String() on it says nothing.
    const failure = describeProofFailure({
      code: -4,
      message: "The user rejected this request.",
    });
    expect(failure.kind).toBe("declined");
    expect(failure.message).not.toContain("[object Object]");
  });

  it("says something useful for an error object with no message at all", () => {
    expect(describeProofFailure({ code: -3 }).message).toContain(
      "without saying why",
    );
  });

  it("passes anything else through with its own message", () => {
    expect(describeProofFailure(new Error("RPC timed out"))).toEqual({
      kind: "failed",
      message: "RPC timed out",
    });
  });
});
