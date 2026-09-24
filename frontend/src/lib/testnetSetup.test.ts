import { afterEach, describe, expect, it, vi } from "vitest";

import {
  TESTNET_USDC_ISSUER,
  decimalToBaseUnits,
  describeSubmitFailure,
  fundWithFriendbot,
  parseAccountSetup,
  readAccountSetup,
  usdcAssetFor,
} from "./testnetSetup";

/**
 * The setup guide tells a new buyer which of three steps is still missing.
 * Getting that wrong either sends them to a faucet they cannot use yet, or
 * offers a trustline to a USDC the API does not accept.
 */

const ADDRESS = "GBRPYHIL2CI3FNQ4BXLFMNDLFJUNPU2HY3ZMFSHONUCEOASW7QC7OX2H";
const USDC_SAC = "CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("parseAccountSetup", () => {
  it("reads an account that does not exist as nothing done", () => {
    expect(parseAccountSetup(null)).toEqual({
      funded: false,
      xlm: null,
      trustline: false,
      usdc: null,
    });
  });

  it("reads a funded account with no trustline", () => {
    expect(
      parseAccountSetup({
        balances: [{ asset_type: "native", balance: "10000.0000000" }],
      }),
    ).toEqual({
      funded: true,
      xlm: "10000.0000000",
      trustline: false,
      usdc: null,
    });
  });

  it("finds the trustline to Circle's USDC and its balance", () => {
    const setup = parseAccountSetup({
      balances: [
        { asset_type: "native", balance: "9999.9" },
        {
          asset_type: "credit_alphanum4",
          asset_code: "USDC",
          asset_issuer: TESTNET_USDC_ISSUER,
          balance: "15.6000000",
        },
      ],
    });
    expect(setup.trustline).toBe(true);
    expect(setup.usdc).toBe("15.6000000");
  });

  it("does not count a USDC from another issuer", () => {
    // Testnet has many tokens named USDC. Only Circle's is what the API takes.
    const setup = parseAccountSetup({
      balances: [
        { asset_type: "native", balance: "1" },
        {
          asset_type: "credit_alphanum4",
          asset_code: "USDC",
          asset_issuer:
            "GA2FWRYEN7P2NRDKRGEYNHJUEBSWYNF25MLB4EFB6J4QNMDBZOTPTJLL",
          balance: "1000.0",
        },
      ],
    });
    expect(setup.trustline).toBe(false);
    expect(setup.usdc).toBeNull();
  });
});

describe("usdcAssetFor", () => {
  // These two import the Stellar SDK to derive a contract id, which is slow to
  // load the first time, so they get more than the default five seconds.
  it("recognises the SAC the live 402 names as Circle's USDC", async () => {
    await expect(usdcAssetFor({ asset: USDC_SAC })).resolves.toEqual({
      code: "USDC",
      issuer: TESTNET_USDC_ISSUER,
    });
  }, 30_000);

  it("offers no trustline for any other asset", async () => {
    await expect(
      usdcAssetFor({
        asset: "CDAYXDIDIINSVQVQRFCH7JSHTFZN4KIZKMNUZRVACHHFLTYGZEZV4OF2",
      }),
    ).resolves.toBeNull();
  }, 30_000);
});

describe("readAccountSetup", () => {
  it("treats Horizon's 404 as an account that is not funded yet", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", { status: 404 }),
    );
    await expect(readAccountSetup(ADDRESS)).resolves.toMatchObject({
      funded: false,
    });
  });

  it("throws on any other failure rather than guessing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("oops", { status: 503 }),
    );
    await expect(readAccountSetup(ADDRESS)).rejects.toThrow("503");
  });
});

describe("fundWithFriendbot", () => {
  it("asks Friendbot for the given address", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}", { status: 200 }));
    await fundWithFriendbot(ADDRESS);
    expect(String(spy.mock.calls[0][0])).toBe(
      `https://friendbot.stellar.org/?addr=${ADDRESS}`,
    );
  });

  it("treats an account that already exists as done", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          extras: { result_codes: { operations: ["op_already_exists"] } },
        }),
        { status: 400 },
      ),
    );
    await expect(fundWithFriendbot(ADDRESS)).resolves.toBeUndefined();
  });

  it("reports a real failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("rate limited", { status: 429 }),
    );
    await expect(fundWithFriendbot(ADDRESS)).rejects.toThrow("429");
  });
});

describe("describeSubmitFailure", () => {
  const horizonError = (codes: unknown) => ({
    response: { data: { extras: { result_codes: codes } } },
  });

  it("explains a missing reserve in plain words", () => {
    expect(
      describeSubmitFailure(
        horizonError({
          transaction: "tx_failed",
          operations: ["op_low_reserve"],
        }),
      ),
    ).toContain("enough XLM");
  });

  it("names the codes for anything else", () => {
    expect(
      describeSubmitFailure(
        horizonError({
          transaction: "tx_failed",
          operations: ["op_no_issuer"],
        }),
      ),
    ).toContain("op_no_issuer");
  });

  it("falls back to the error message", () => {
    expect(describeSubmitFailure(new Error("network down"))).toBe(
      "network down",
    );
  });
});

describe("decimalToBaseUnits", () => {
  it("converts Horizon balances exactly", () => {
    expect(decimalToBaseUnits("15.6000000")).toBe(BigInt(156000000));
    expect(decimalToBaseUnits("0.1")).toBe(BigInt(1000000));
    expect(decimalToBaseUnits("0")).toBe(BigInt(0));
    expect(decimalToBaseUnits("10")).toBe(BigInt(100000000));
  });

  it("ignores digits past the asset's precision instead of rounding up", () => {
    expect(decimalToBaseUnits("0.12345678")).toBe(BigInt(1234567));
  });
});
