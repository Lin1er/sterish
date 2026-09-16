import { describe, expect, it } from "vitest";

import type { PaymentRequired } from "./types";
import {
  classifyPaymentFailure,
  decodePaymentRequired,
  decodeSettlementReceipt,
  formatBaseUnits,
  selectRequirement,
} from "./x402";

/**
 * The parts of the buy flow that decide what a visitor is told before they
 * sign: the price, which terms are payable, and what went wrong. None of it
 * needs a wallet, so all of it is tested here.
 */

const TERMS = {
  scheme: "exact",
  network: "stellar:testnet",
  amount: "1000000",
  asset: "CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA",
  payTo: "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU",
  maxTimeoutSeconds: 300,
  extra: { areFeesSponsored: true },
};

function encode(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString("base64");
}

describe("decodePaymentRequired", () => {
  it("reads the challenge spec 3.7 captured from the reference server", () => {
    const decoded = decodePaymentRequired(
      encode({
        x402Version: 2,
        error: "Payment required",
        resource: {
          url: "https://api/use/x/1.0.0",
          description: "License for x@1.0.0",
          mimeType: "application/json",
        },
        accepts: [TERMS],
      }),
    );
    expect(decoded?.x402Version).toBe(2);
    expect(decoded?.accepts).toEqual([TERMS]);
    expect(decoded?.resource.description).toBe("License for x@1.0.0");
  });

  it("returns null for a header that is not base64 JSON", () => {
    expect(decodePaymentRequired("%%%")).toBeNull();
    expect(decodePaymentRequired(encode("a string"))).toBeNull();
  });

  it("returns null when no entry has usable terms", () => {
    // Paying against guessed terms is worse than not paying.
    expect(
      decodePaymentRequired(
        encode({ x402Version: 2, accepts: [{ ...TERMS, amount: "0.10" }] }),
      ),
    ).toBeNull();
    expect(
      decodePaymentRequired(encode({ x402Version: 2, accepts: [] })),
    ).toBeNull();
    expect(decodePaymentRequired(encode({ accepts: [TERMS] }))).toBeNull();
  });

  it("drops malformed entries but keeps the usable ones", () => {
    const decoded = decodePaymentRequired(
      encode({ x402Version: 2, accepts: [{ scheme: "exact" }, TERMS] }),
    );
    expect(decoded?.accepts).toHaveLength(1);
  });

  it("decodes UTF-8 descriptions without mangling them", () => {
    const decoded = decodePaymentRequired(
      encode({
        x402Version: 2,
        resource: { description: "Licence für café@1.0.0" },
        accepts: [TERMS],
      }),
    );
    expect(decoded?.resource.description).toBe("Licence für café@1.0.0");
  });
});

describe("selectRequirement", () => {
  const base: PaymentRequired = {
    x402Version: 2,
    resource: { url: "", description: "", mimeType: "" },
    accepts: [TERMS],
  };

  it("picks exact on the network the dashboard is built for", () => {
    expect(selectRequirement(base)).toEqual(TERMS);
  });

  it("refuses terms on another network", () => {
    // A testnet page must never sign a mainnet transfer.
    expect(
      selectRequirement({
        ...base,
        accepts: [{ ...TERMS, network: "stellar:pubnet" }],
      }),
    ).toBeNull();
  });

  it("refuses a scheme it cannot pay", () => {
    expect(
      selectRequirement({ ...base, accepts: [{ ...TERMS, scheme: "upto" }] }),
    ).toBeNull();
  });
});

describe("formatBaseUnits", () => {
  it("shows the spec's example price as 0.10", () => {
    expect(formatBaseUnits("1000000")).toBe("0.10");
  });

  it("never rounds away a digit the wallet will charge", () => {
    expect(formatBaseUnits("1234567")).toBe("0.1234567");
    expect(formatBaseUnits("1")).toBe("0.0000001");
  });

  it("handles whole amounts and large balances exactly", () => {
    expect(formatBaseUnits("0")).toBe("0.00");
    expect(formatBaseUnits("10000000")).toBe("1.00");
    expect(formatBaseUnits(BigInt("123456789012345678"))).toBe(
      "12345678901.2345678",
    );
  });
});

describe("decodeSettlementReceipt", () => {
  it("reads the facilitator receipt", () => {
    expect(
      decodeSettlementReceipt(encode({ success: true, transaction: "ab12" })),
    ).toMatchObject({ transaction: "ab12" });
  });

  it("treats a missing or unreadable receipt as absent", () => {
    expect(decodeSettlementReceipt(null)).toBeNull();
    expect(decodeSettlementReceipt("%%%")).toBeNull();
  });
});

describe("classifyPaymentFailure", () => {
  it("reads the kit's own cancel as a decision", () => {
    expect(classifyPaymentFailure({ code: -1, message: "closed" }).kind).toBe(
      "declined",
    );
  });

  it("reads a wallet's rejection message as a decision", () => {
    expect(
      classifyPaymentFailure({ code: -4, message: "The user rejected this request." })
        .kind,
    ).toBe("declined");
  });

  it("recognises an underfunded transfer", () => {
    const failure = classifyPaymentFailure(
      new Error(
        "Stellar simulation failed with error message: HostError: Error(Contract, #10) balance is not sufficient to spend",
      ),
    );
    expect(failure.kind).toBe("insufficient_funds");
    expect(failure.message).toContain("Nothing was paid");
  });

  it("recognises a missing trustline", () => {
    expect(
      classifyPaymentFailure(new Error("trustline entry is missing for account"))
        .kind,
    ).toBe("insufficient_funds");
  });

  it("passes anything else through with its own message", () => {
    expect(classifyPaymentFailure(new Error("RPC timed out"))).toEqual({
      kind: "failed",
      message: "RPC timed out",
    });
  });
});
