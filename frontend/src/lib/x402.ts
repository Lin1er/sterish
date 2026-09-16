/**
 * The buyer's side of x402 on Stellar, run from the browser.
 *
 * STE-22 asks for the 402, pay, 200 loop to be driven from the dashboard with
 * the visitor's own wallet. That turned out to need no server help at all:
 * `@x402/stellar` builds the USDC `transfer`, and the only thing it needs from
 * the buyer is somebody to sign one Soroban auth entry, which every wallet in
 * Stellar Wallets Kit can do. The facilitator sponsors the network fee, so the
 * buyer holds USDC and nothing else.
 *
 * The payment libraries are imported lazily, the same way the wallet kit is.
 * They pull in a second copy of the Stellar SDK, and nobody who only reads the
 * registry should download it.
 *
 * Everything here that does not touch the network is exported and pure, so the
 * parts that decide what a visitor is told (the price, the network check, the
 * error wording) are unit tested without a wallet.
 */

import type {
  PaymentRequired,
  PaymentRequirement,
  SettlementReceipt,
} from "./types";
import {
  NETWORK_PASSPHRASE,
  RPC_URL,
  X402_NETWORK,
  signAuthEntry,
  walletErrorMessage,
} from "./wallet";

/** USDC on Stellar has 7 decimals: `1000000` base units is 0.10. */
export const USDC_DECIMALS = 7;

const UTF8 = new TextDecoder();

function decodeBase64Json(value: string): unknown {
  const binary = atob(value.trim());
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return JSON.parse(UTF8.decode(bytes));
}

function encodeBase64Json(value: unknown): string {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function isRequirement(value: unknown): value is PaymentRequirement {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    typeof r.scheme === "string" &&
    typeof r.network === "string" &&
    typeof r.amount === "string" &&
    /^\d+$/.test(r.amount) &&
    typeof r.asset === "string" &&
    typeof r.payTo === "string"
  );
}

/**
 * Decode the `PAYMENT-REQUIRED` header of a 402.
 *
 * Returns null for anything that is not a usable v2 challenge rather than
 * throwing. The caller turns that into a named error, because "the API asked
 * for payment in a shape we cannot read" must never become a payment made
 * against guessed terms.
 */
export function decodePaymentRequired(header: string): PaymentRequired | null {
  let parsed: unknown;
  try {
    parsed = decodeBase64Json(header);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const body = parsed as Record<string, unknown>;
  if (typeof body.x402Version !== "number" || !Array.isArray(body.accepts)) {
    return null;
  }
  const accepts = body.accepts.filter(isRequirement).map((r) => ({
    ...r,
    maxTimeoutSeconds:
      typeof r.maxTimeoutSeconds === "number" ? r.maxTimeoutSeconds : 300,
    extra:
      typeof r.extra === "object" && r.extra !== null
        ? (r.extra as Record<string, unknown>)
        : {},
  }));
  if (accepts.length === 0) return null;
  const resource = (body.resource ?? {}) as Record<string, unknown>;
  return {
    x402Version: body.x402Version,
    error: typeof body.error === "string" ? body.error : undefined,
    resource: {
      url: String(resource.url ?? ""),
      description: String(resource.description ?? ""),
      mimeType: String(resource.mimeType ?? ""),
    },
    accepts,
  };
}

/** Decode `X-PAYMENT-RESPONSE`. A receipt we cannot read is simply absent. */
export function decodeSettlementReceipt(
  header: string | null,
): SettlementReceipt | null {
  if (!header) return null;
  try {
    const parsed = decodeBase64Json(header);
    return typeof parsed === "object" && parsed !== null
      ? (parsed as SettlementReceipt)
      : null;
  } catch {
    return null;
  }
}

/**
 * The one requirement this dashboard can pay: the `exact` scheme on the
 * network the dashboard is built for.
 *
 * The network check is not decoration. A testnet dashboard that signed
 * whatever a 402 asked for could be pointed at an API advertising mainnet
 * terms, and the visitor would be approving a real transfer from a page that
 * says "Stellar Testnet" in its footer.
 */
export function selectRequirement(
  paymentRequired: PaymentRequired,
): PaymentRequirement | null {
  return (
    paymentRequired.accepts.find(
      (r) => r.scheme === "exact" && r.network === X402_NETWORK,
    ) ?? null
  );
}

/**
 * Base units to a human amount, without floating point.
 *
 * Money is shown with at least two decimals and never rounded: `1000000`
 * becomes "0.10", `1234567` becomes "0.1234567". Rounding a price the wallet is
 * about to sign would show one number and charge another.
 */
export function formatBaseUnits(
  amount: string | bigint,
  decimals: number = USDC_DECIMALS,
): string {
  const value = typeof amount === "bigint" ? amount : BigInt(amount);
  const negative = value < BigInt(0);
  const digits = (negative ? -value : value)
    .toString()
    .padStart(decimals + 1, "0");
  const whole = digits.slice(0, digits.length - decimals);
  let fraction = digits.slice(digits.length - decimals).replace(/0+$/, "");
  if (fraction.length < 2) fraction = fraction.padEnd(2, "0");
  return `${negative ? "-" : ""}${whole}.${fraction}`;
}

/** Why a payment could not be built or signed, in terms a visitor can act on. */
export type PaymentFailure =
  | { kind: "declined"; message: string }
  | { kind: "wallet_unavailable"; message: string }
  | { kind: "insufficient_funds"; message: string }
  | { kind: "failed"; message: string };

/**
 * Sort a failure from the wallet or from `@x402/stellar` into something the UI
 * can word.
 *
 * Wallets do not agree on how to say "the user said no", so this reads the
 * message and not the code. The code is useless here: the kit's `parseError`
 * fills in `-1` for any error that has none, so "Freighter is not connected"
 * arrives as `{ code: -1 }` exactly like a closed modal does. Reading -1 as a
 * refusal told somebody with no wallet installed that they had declined.
 *
 * An underfunded payment surfaces as a failed simulation of the USDC transfer,
 * since @x402/stellar simulates before asking for a signature. The contract's
 * wording varies, so a few stable fragments are matched.
 */
export function classifyPaymentFailure(cause: unknown): PaymentFailure {
  const message = walletErrorMessage(cause);
  if (
    /not connected|not installed|not available|no wallet|locked/i.test(message)
  ) {
    return {
      kind: "wallet_unavailable",
      message:
        "Your wallet did not respond. Make sure the wallet extension is installed, unlocked and connected to this site, then try again. Nothing was paid.",
    };
  }
  if (/reject|declin|denied|cancel/i.test(message)) {
    return {
      kind: "declined",
      message: "You declined the signature in your wallet. Nothing was paid.",
    };
  }
  if (/balance|insufficient|trustline|resulting balance/i.test(message)) {
    return {
      kind: "insufficient_funds",
      message:
        "The USDC transfer could not be simulated, which usually means this account holds too little USDC or has no USDC trustline. Nothing was paid.",
    };
  }
  return {
    kind: "failed",
    // An error object with no message stringifies to "[object Object]", which
    // tells a buyer nothing and reads like a bug in this page.
    message:
      message === "[object Object]"
        ? "The wallet returned an error without saying why. Nothing was paid."
        : message,
  };
}

/**
 * Build and sign the `X-PAYMENT` header for one challenge.
 *
 * Uses `x402Client` rather than calling the scheme directly, because the client
 * is what wraps the signed transfer with `resource` and `accepted`, and the
 * facilitator verifies against those. This is the same assembly the reference
 * buyer in `demo/x402-buyer/buy.js` runs, with the wallet standing in for the
 * secret key.
 */
export async function createPaymentHeader(
  paymentRequired: PaymentRequired,
  payer: string,
): Promise<string> {
  const requirement = selectRequirement(paymentRequired);
  if (!requirement) {
    throw new Error(
      `The API asked for payment on a network this dashboard does not pay on (expected ${X402_NETWORK})`,
    );
  }

  const [{ x402Client }, { ExactStellarScheme }] = await Promise.all([
    import("@x402/core/client"),
    import("@x402/stellar/exact/client"),
  ]);

  const scheme = new ExactStellarScheme(
    {
      address: payer,
      signAuthEntry: (authEntry, opts) =>
        signAuthEntry(authEntry, {
          address: payer,
          networkPassphrase: opts?.networkPassphrase ?? NETWORK_PASSPHRASE,
        }),
    },
    { url: RPC_URL },
  );
  const client = new x402Client().register(X402_NETWORK, scheme);

  // Only the requirement this page agreed to show is offered to the client, so
  // it cannot select a different entry from `accepts` than the one the visitor
  // saw priced on screen.
  const payload = await client.createPaymentPayload({
    ...paymentRequired,
    accepts: [requirement],
  } as Parameters<typeof client.createPaymentPayload>[0]);

  return encodeBase64Json(payload);
}

/**
 * The account's USDC balance, in base units, read from the SAC.
 *
 * Asked before the wallet prompt so "you do not have enough" is said in plain
 * words up front, instead of arriving as a failed simulation after a signature
 * request. Returns null when the read fails: the check is a courtesy, and an
 * RPC hiccup must not stop somebody who can in fact pay.
 */
export async function readTokenBalance(
  asset: string,
  account: string,
): Promise<bigint | null> {
  try {
    const {
      Account,
      Contract,
      TransactionBuilder,
      nativeToScVal,
      rpc,
      scValToNative,
    } = await import("@stellar/stellar-sdk");
    const server = new rpc.Server(RPC_URL);
    // A simulation needs a source account but never checks its sequence, so a
    // throwaway Account object with sequence 0 is enough and costs no read.
    const tx = new TransactionBuilder(new Account(account, "0"), {
      fee: "100",
      networkPassphrase: NETWORK_PASSPHRASE,
    })
      .addOperation(
        new Contract(asset).call(
          "balance",
          nativeToScVal(account, { type: "address" }),
        ),
      )
      .setTimeout(30)
      .build();
    const simulation = await server.simulateTransaction(tx);
    if (!rpc.Api.isSimulationSuccess(simulation) || !simulation.result) {
      return null;
    }
    const value: unknown = scValToNative(simulation.result.retval);
    return typeof value === "bigint" ? value : BigInt(String(value));
  } catch {
    return null;
  }
}
