/**
 * Getting a fresh testnet wallet ready to buy a licence, from the dashboard.
 *
 * STE-22 asks for the whole third-party scenario (new agent wallet, test USDC,
 * check, buy) to run from the UI without a CLI. Three things stand between a
 * new Freighter account and a payment, and this file handles the two that can
 * be done from here:
 *
 * 1. The account must exist, which on testnet means Friendbot funding it.
 * 2. It needs a trustline to the exact USDC the API charges in.
 * 3. It needs USDC. Circle's faucet sits behind a captcha, so that step is a
 *    link, not a button.
 *
 * Testnet only. On mainnet nothing here is offered: there is no Friendbot, and
 * a dashboard that adds trustlines for real money on a click is not a
 * convenience anybody should want.
 */

import type { PaymentRequirement } from "./types";
import {
  HORIZON_URL,
  IS_MAINNET,
  NETWORK_PASSPHRASE,
  signTransaction,
} from "./wallet";

/**
 * Circle's USDC issuer on testnet. Its SAC is `CBIELTK6...DAMA`, the asset the
 * API's 402 names, and `usdcAssetFor` checks that relationship instead of
 * trusting this constant: testnet is full of tokens called USDC from other
 * issuers, and a trustline to the wrong one would leave the buyer holding
 * something the API does not accept.
 */
export const TESTNET_USDC_ISSUER =
  "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5";

export const USDC_FAUCET_URL = "https://faucet.circle.com/";

const FRIENDBOT_URL = "https://friendbot.stellar.org";

/** Setup is only ever offered on testnet. */
export const SETUP_AVAILABLE = !IS_MAINNET;

export interface AccountSetup {
  /** The account exists on the ledger. */
  funded: boolean;
  /** Native balance as Horizon reports it, a decimal string. */
  xlm: string | null;
  /** A trustline to the USDC the API charges in exists. */
  trustline: boolean;
  /** USDC balance on that trustline, a decimal string. */
  usdc: string | null;
}

interface HorizonBalance {
  asset_type: string;
  asset_code?: string;
  asset_issuer?: string;
  balance: string;
}

/**
 * Read the three facts out of a Horizon account record. Pure, so the parsing
 * is tested without a network.
 */
export function parseAccountSetup(
  account: { balances?: HorizonBalance[] } | null,
  issuer: string = TESTNET_USDC_ISSUER,
): AccountSetup {
  if (!account) {
    return { funded: false, xlm: null, trustline: false, usdc: null };
  }
  const balances = account.balances ?? [];
  const native = balances.find((b) => b.asset_type === "native");
  const usdc = balances.find(
    (b) => b.asset_code === "USDC" && b.asset_issuer === issuer,
  );
  return {
    funded: true,
    xlm: native?.balance ?? null,
    trustline: usdc !== undefined,
    usdc: usdc?.balance ?? null,
  };
}

/**
 * Horizon's decimal balance ("15.6000000") in 7-decimal base units, without
 * floating point, so it can be compared with a 402's `amount` exactly.
 */
export function decimalToBaseUnits(value: string, decimals = 7): bigint {
  const [whole, fraction = ""] = value.trim().split(".");
  const padded = (fraction + "0".repeat(decimals)).slice(0, decimals);
  return (
    BigInt(whole || "0") * BigInt(10) ** BigInt(decimals) +
    BigInt(padded || "0")
  );
}

/** Horizon answers 404 for an account that does not exist yet. */
export async function readAccountSetup(address: string): Promise<AccountSetup> {
  const response = await fetch(`${HORIZON_URL}/accounts/${address}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  if (response.status === 404) return parseAccountSetup(null);
  if (!response.ok) {
    throw new Error(`Horizon answered ${response.status} for this account`);
  }
  return parseAccountSetup(await response.json());
}

/**
 * The classic asset behind a payment requirement, when it is Circle's USDC.
 *
 * Returns null for anything else, and the UI then offers no trustline button.
 * The check is the SAC address derived from code and issuer: if it does not
 * equal the `asset` in the 402, this is not the asset being charged.
 */
export async function usdcAssetFor(
  requirement: Pick<PaymentRequirement, "asset">,
): Promise<{ code: "USDC"; issuer: string } | null> {
  const { Asset } = await import("@stellar/stellar-sdk");
  const asset = new Asset("USDC", TESTNET_USDC_ISSUER);
  return asset.contractId(NETWORK_PASSPHRASE) === requirement.asset
    ? { code: "USDC", issuer: TESTNET_USDC_ISSUER }
    : null;
}

/**
 * Fund a new testnet account with Friendbot.
 *
 * Friendbot refuses an account that already exists. That is the outcome the
 * caller wanted anyway, so it is not reported as a failure: the next account
 * read shows the truth either way.
 */
export async function fundWithFriendbot(address: string): Promise<void> {
  if (!SETUP_AVAILABLE) throw new Error("Friendbot only exists on testnet");
  const response = await fetch(
    `${FRIENDBOT_URL}/?addr=${encodeURIComponent(address)}`,
    { signal: AbortSignal.timeout(30_000) },
  );
  if (response.ok) return;
  const body = await response.text().catch(() => "");
  if (/already exist|createAccountAlreadyExist|op_already_exists/i.test(body)) {
    return;
  }
  throw new Error(
    `Friendbot could not fund this account (${response.status}). Try again in a minute.`,
  );
}

/**
 * Pull a readable reason out of a failed Horizon submission. Horizon puts the
 * useful part in `extras.result_codes`, not in the message.
 */
export function describeSubmitFailure(cause: unknown): string {
  const extras = (
    cause as { response?: { data?: { extras?: { result_codes?: unknown } } } }
  )?.response?.data?.extras;
  const codes = extras?.result_codes as
    { transaction?: string; operations?: string[] } | undefined;
  if (codes?.operations?.includes("op_low_reserve")) {
    return "The account does not hold enough XLM for the reserve a trustline needs. Fund it first.";
  }
  if (codes?.transaction === "tx_bad_seq") {
    return "The account changed while the trustline was being signed. Try again.";
  }
  if (codes) {
    return `The network refused the trustline (${[codes.transaction, ...(codes.operations ?? [])].filter(Boolean).join(", ")}).`;
  }
  return cause instanceof Error ? cause.message : String(cause);
}

/**
 * Add a trustline to Circle's testnet USDC, signed by the connected wallet.
 * Returns the transaction hash.
 */
export async function addUsdcTrustline(address: string): Promise<string> {
  if (!SETUP_AVAILABLE) throw new Error("Trustline setup is testnet only");
  const { Asset, BASE_FEE, Horizon, Operation, TransactionBuilder } =
    await import("@stellar/stellar-sdk");
  const server = new Horizon.Server(HORIZON_URL);
  const account = await server.loadAccount(address);
  const tx = new TransactionBuilder(account, {
    fee: BASE_FEE,
    networkPassphrase: NETWORK_PASSPHRASE,
  })
    .addOperation(
      Operation.changeTrust({ asset: new Asset("USDC", TESTNET_USDC_ISSUER) }),
    )
    .setTimeout(180)
    .build();

  const signed = await signTransaction(tx.toXDR(), { address });
  const envelope = TransactionBuilder.fromXDR(signed, NETWORK_PASSPHRASE);
  try {
    const result = await server.submitTransaction(envelope);
    return result.hash;
  } catch (cause) {
    throw new Error(describeSubmitFailure(cause));
  }
}
