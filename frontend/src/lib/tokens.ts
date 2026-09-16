/**
 * Licences held by an address, read straight from the tokens contract.
 *
 * Temporary, and says so on screen. The API has no "licences of this address"
 * endpoint yet (STE-46); until it does, the page reads every token record and
 * keeps the licences owned by the address. That is one simulation per token
 * ever minted, which is fine at a few dozen tokens (19 took 0.47s on
 * 2026-09-16) and is exactly why STE-46 exists.
 *
 * Reads only. Every call is a `simulateTransaction` from a throwaway source
 * account, the same way the API reads the chain, so no key is involved.
 */

import { NETWORK_PASSPHRASE, RPC_URL } from "./wallet";

/** Tokens v2, deployed in STE-44. Overridable for a redeploy. */
export const TOKENS_CONTRACT_ID =
  process.env.NEXT_PUBLIC_TOKENS_CONTRACT_ID ??
  "CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T";

/**
 * `TokenError::TokenNotFound = 2` in contracts/tokens/src/data.rs. Only this
 * error means "no token at this id"; every other contract error is a real
 * failure and must not be skipped as if the slot were empty.
 */
const TOKEN_NOT_FOUND = /Error\(Contract, #2\)/;

/** Simultaneous simulations. Enough to be quick, few enough to be polite. */
const CONCURRENCY = 8;

export interface Licence {
  tokenId: number;
  skillId: string;
  version: string;
  owner: string;
  /** Ledger timestamp, unix seconds. */
  mintedAt: number;
}

export interface LicenceScan {
  licences: Licence[];
  /** How many token records were read to produce the list. */
  scanned: number;
}

/** A classic `G...` account. Contracts and muxed accounts hold no licences. */
export function isAccountAddress(value: string): boolean {
  return /^G[A-Z2-7]{55}$/.test(value);
}

/**
 * One `get_token` result, as `scValToNative` decodes it, into a licence. Returns
 * null for a VERIFIED badge or anything that does not have the licence shape.
 *
 * `kind` arrives as a one-element array (`["License"]`) because the contract
 * enum is a unit variant.
 */
export function parseLicence(record: unknown): Licence | null {
  if (typeof record !== "object" || record === null) return null;
  const r = record as Record<string, unknown>;
  const kind = Array.isArray(r.kind) ? r.kind[0] : r.kind;
  if (kind !== "License") return null;
  if (
    typeof r.skill_id !== "string" ||
    typeof r.version !== "string" ||
    typeof r.owner !== "string"
  ) {
    return null;
  }
  return {
    tokenId: Number(r.token_id),
    skillId: r.skill_id,
    version: r.version,
    owner: r.owner,
    mintedAt: Number(r.minted_at),
  };
}

/** A contract read: method plus native arguments in, decoded result out. */
export type ContractCall = (
  method: string,
  args: Array<{ value: number; type: "u32" }>,
) => Promise<unknown>;

/** A read that failed for a reason other than the contract's own answer. */
export class ChainReadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChainReadError";
  }
}

/** The real contract read, over Soroban RPC. */
async function rpcCall(
  method: string,
  args: Array<{ value: number; type: "u32" }>,
): Promise<unknown> {
  const {
    Account,
    Contract,
    TransactionBuilder,
    nativeToScVal,
    rpc,
    scValToNative,
  } = await import("@stellar/stellar-sdk");
  const server = new rpc.Server(RPC_URL);
  const tx = new TransactionBuilder(
    new Account(
      "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU",
      "0",
    ),
    { fee: "100", networkPassphrase: NETWORK_PASSPHRASE },
  )
    .addOperation(
      new Contract(TOKENS_CONTRACT_ID).call(
        method,
        ...args.map((a) => nativeToScVal(a.value, { type: a.type })),
      ),
    )
    .setTimeout(30)
    .build();

  let simulation;
  try {
    simulation = await server.simulateTransaction(tx);
  } catch (cause) {
    throw new ChainReadError(
      `Soroban RPC is unreachable: ${cause instanceof Error ? cause.message : String(cause)}`,
    );
  }
  if (rpc.Api.isSimulationError(simulation)) {
    // A contract error is an answer, not an outage; the caller decides what
    // it means. Anything else is a failed read.
    if (TOKEN_NOT_FOUND.test(simulation.error)) return { contractError: true };
    throw new ChainReadError(
      `The tokens contract read failed: ${simulation.error}`,
    );
  }
  if (!rpc.Api.isSimulationSuccess(simulation) || !simulation.result) {
    throw new ChainReadError("The tokens contract returned no result");
  }
  return scValToNative(simulation.result.retval);
}

/**
 * Every licence `address` holds, newest first.
 *
 * `total_supply` is the number of tokens ever minted, and ids run from 1 to it
 * with nothing ever burned, so every id in that range is read. A
 * `TokenNotFound` is still tolerated rather than fatal: a mint landing between
 * the supply read and the token reads must not turn the page into an error. A
 * failed read throws: an empty list must only ever mean the chain was read and
 * holds nothing for this address.
 */
export async function readLicences(
  address: string,
  call: ContractCall = rpcCall,
): Promise<LicenceScan> {
  const supply = Number(await call("total_supply", []));
  if (!Number.isInteger(supply) || supply < 0) {
    throw new ChainReadError(`total_supply returned ${String(supply)}`);
  }

  const ids = Array.from({ length: supply }, (_, i) => i + 1);
  const records: unknown[] = [];
  for (let start = 0; start < ids.length; start += CONCURRENCY) {
    const batch = ids.slice(start, start + CONCURRENCY);
    records.push(
      ...(await Promise.all(
        batch.map((id) => call("get_token", [{ value: id, type: "u32" }])),
      )),
    );
  }

  const found = records.filter(
    (r) => !(typeof r === "object" && r !== null && "contractError" in r),
  );
  const licences = found
    .map(parseLicence)
    .filter((l): l is Licence => l !== null && l.owner === address)
    .sort((a, b) => b.mintedAt - a.mintedAt || b.tokenId - a.tokenId);

  return { licences, scanned: found.length };
}
