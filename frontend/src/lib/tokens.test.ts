import { describe, expect, it } from "vitest";

import {
  ChainReadError,
  isAccountAddress,
  parseLicence,
  readLicences,
  type ContractCall,
} from "./tokens";

/**
 * The licences page shows what an address holds. The two failures that matter:
 * listing somebody else's licence as theirs, and turning a failed read into
 * "holds nothing".
 */

const ME = "GDAVKROBU6VGWMAY36YMHQ6LV7XD7D5R5T3LJTTEBJKX3EURZAEDHSPL";
const OTHER = "GCF76SG6QUBTJHK6AEFPS22TOB6JO5TKXXR5FW3QSDFOFLNXNLCJTXSC";

function token(
  id: number,
  kind: "License" | "Verified",
  owner: string,
  mintedAt: number,
  skill = `org.example.skill-${id}`,
) {
  return {
    kind: [kind],
    minted_at: BigInt(mintedAt),
    owner,
    skill_id: skill,
    token_id: id,
    version: "1.0.0",
  };
}

/** A fake contract holding `tokens`; total_supply is the count, ids from 1. */
function contract(
  tokens: ReturnType<typeof token>[],
  supply = tokens.length,
): ContractCall {
  return async (method, args) => {
    if (method === "total_supply") return supply;
    const id = args[0].value;
    return tokens.find((t) => t.token_id === id) ?? { contractError: true };
  };
}

describe("isAccountAddress", () => {
  it("accepts a G account", () => {
    expect(isAccountAddress(ME)).toBe(true);
  });

  it("refuses contracts, muxed accounts, and anything else", () => {
    expect(
      isAccountAddress(
        "CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T",
      ),
    ).toBe(false);
    expect(isAccountAddress(`M${ME.slice(1)}AAAAAAAAAAAA`)).toBe(false);
    expect(isAccountAddress(ME.toLowerCase())).toBe(false);
    expect(isAccountAddress("hello")).toBe(false);
    expect(isAccountAddress("")).toBe(false);
  });
});

describe("parseLicence", () => {
  it("reads the shape scValToNative produces", () => {
    expect(parseLicence(token(19, "License", ME, 1789548592))).toEqual({
      tokenId: 19,
      skillId: "org.example.skill-19",
      version: "1.0.0",
      owner: ME,
      mintedAt: 1789548592,
    });
  });

  it("ignores VERIFIED badges", () => {
    expect(parseLicence(token(1, "Verified", ME, 1))).toBeNull();
  });

  it("ignores anything that is not a token record", () => {
    expect(parseLicence(null)).toBeNull();
    expect(parseLicence({ contractError: true })).toBeNull();
    expect(parseLicence({ kind: ["License"], owner: ME })).toBeNull();
  });
});

describe("readLicences", () => {
  it("returns only licences owned by the address, newest first", async () => {
    const scan = await readLicences(
      ME,
      contract([
        token(1, "Verified", ME, 100),
        token(2, "License", ME, 200, "org.example.older"),
        token(3, "License", OTHER, 300),
        token(4, "License", ME, 400, "org.example.newer"),
      ]),
    );
    expect(scan.licences.map((l) => l.skillId)).toEqual([
      "org.example.newer",
      "org.example.older",
    ]);
    expect(scan.scanned).toBe(4);
  });

  it("reads every id from 1 to total_supply", async () => {
    const calls: number[] = [];
    const inner = contract([
      token(1, "License", ME, 1),
      token(2, "License", ME, 2),
      token(3, "License", ME, 3),
    ]);
    const scan = await readLicences(ME, async (method, args) => {
      if (method === "get_token") calls.push(args[0].value);
      return inner(method, args);
    });
    expect(calls.sort((a, b) => a - b)).toEqual([1, 2, 3]);
    expect(scan.scanned).toBe(3);
  });

  it("tolerates a token that is missing when read, instead of failing", async () => {
    // A supply read that races ahead of the token reads.
    const scan = await readLicences(
      ME,
      contract([token(1, "License", ME, 1)], 2),
    );
    expect(scan.licences).toHaveLength(1);
    expect(scan.scanned).toBe(1);
  });

  it("answers an empty list for an address that holds nothing", async () => {
    const scan = await readLicences(
      ME,
      contract([token(1, "License", OTHER, 1)]),
    );
    expect(scan.licences).toEqual([]);
    expect(scan.scanned).toBe(1);
  });

  it("handles a contract that has minted nothing", async () => {
    await expect(readLicences(ME, contract([]))).resolves.toEqual({
      licences: [],
      scanned: 0,
    });
  });

  it("throws when a read fails, instead of reporting no licences", async () => {
    const failing: ContractCall = async (method, args) => {
      if (method === "total_supply") return 3;
      if (args[0].value === 2) throw new ChainReadError("RPC down");
      return token(args[0].value, "License", ME, 1);
    };
    await expect(readLicences(ME, failing)).rejects.toThrow("RPC down");
  });

  it("throws on a nonsensical supply", async () => {
    await expect(
      readLicences(ME, async () => "not a number"),
    ).rejects.toBeInstanceOf(ChainReadError);
  });
});
