/**
 * Stellar Wallets Kit, loaded lazily and only in the browser.
 *
 * Three things about version 2.x drove the shape of this file, and all three
 * were read out of the installed package rather than from a tutorial:
 *
 * 1. `StellarWalletsKit` is a static class with `init()`, not a constructor.
 *    Older examples showing `new StellarWalletsKit({...})` and `kit.openModal`
 *    describe version 1 and do not compile against what is installed.
 * 2. It renders its modal with preact and touches `document` on import, so it
 *    is imported dynamically. That also keeps it out of the first load: the
 *    package pulls in a large wallet tree that nobody needs until they click
 *    Connect.
 * 3. It persists `activeAddress` and `selectedModuleId` to localStorage by
 *    itself, guarding every access, so a session survives a refresh with no
 *    persistence code of our own. See its state/effects module.
 */

type KitModule = typeof import("@creit.tech/stellar-wallets-kit");

/** Testnet unless told otherwise: the contracts STE-13 deployed live there. */
const NETWORK = process.env.NEXT_PUBLIC_STELLAR_NETWORK ?? "testnet";

export const IS_MAINNET = NETWORK === "mainnet" || NETWORK === "public";

/** stellar.expert splits its explorer by network, so links follow the config. */
export const EXPLORER_BASE = IS_MAINNET
  ? "https://stellar.expert/explorer/public"
  : "https://stellar.expert/explorer/testnet";

/**
 * The passphrase every signature is bound to. A signature made for one network
 * is invalid on the other, so this is passed to the wallet explicitly rather
 * than left to whichever network the wallet happens to be set to.
 */
export const NETWORK_PASSPHRASE = IS_MAINNET
  ? "Public Global Stellar Network ; September 2015"
  : "Test SDF Network ; September 2015";

/** The CAIP-2 id x402 uses for the same network (spec §3.7). */
export const X402_NETWORK = IS_MAINNET ? "stellar:pubnet" : "stellar:testnet";

/**
 * Soroban RPC for the client's own reads: the USDC balance before a purchase,
 * and the simulation @x402/stellar runs while building the payment. Mainnet has
 * no public default, so a mainnet build without this variable fails loudly at
 * the first read instead of quietly asking testnet.
 */
export const RPC_URL =
  process.env.NEXT_PUBLIC_STELLAR_RPC_URL ??
  (IS_MAINNET ? "" : "https://soroban-testnet.stellar.org");

/**
 * Horizon, for the classic side of an account: whether it exists, its XLM, and
 * its trustlines. Soroban RPC does not answer those questions.
 */
export const HORIZON_URL =
  process.env.NEXT_PUBLIC_STELLAR_HORIZON_URL ??
  (IS_MAINNET
    ? "https://horizon.stellar.org"
    : "https://horizon-testnet.stellar.org");

let kitPromise: Promise<KitModule> | null = null;

/**
 * Import and initialise the kit exactly once per page load.
 *
 * The whole module comes back, not just the class, because callers also need
 * its `KitEventType` enum, which is a runtime value and so cannot be reached
 * through a type-only import.
 *
 * The promise itself is memoised rather than the resolved value, so two
 * components calling this in the same tick share one import and one `init`
 * instead of racing to initialise the same static class twice.
 */
export function loadKit(): Promise<KitModule> {
  if (typeof window === "undefined") {
    return Promise.reject(
      new Error("The wallet kit is browser only and cannot run on the server"),
    );
  }

  // Two entry points, because the package's exports map keeps the wallet
  // module helpers on their own subpath and does not re-export them from the
  // root. Importing them together costs one round trip rather than two.
  kitPromise ??= Promise.all([
    import("@creit.tech/stellar-wallets-kit"),
    import("@creit.tech/stellar-wallets-kit/modules/utils"),
  ]).then(([mod, { defaultModules }]) => {
    // defaultModules() is every wallet that needs no extra configuration, and
    // it deliberately excludes WalletConnect, which would need a projectId we
    // do not have. sep43Modules() was the other candidate and was rejected:
    // it is only Freighter and D'CENT, which would drop xBull, Albedo, Lobstr
    // and Hana from the picker for no gain.
    mod.StellarWalletsKit.init({
      modules: defaultModules(),
      network: IS_MAINNET ? mod.Networks.PUBLIC : mod.Networks.TESTNET,
    });

    return mod;
  });

  return kitPromise;
}

/**
 * The kit rejects with a plain object, not an Error, and closing the modal is
 * one of those rejections. Treating a cancel as a failure would paint an error
 * banner every time somebody changes their mind, so it is detected by shape.
 */
export function isUserCancelled(cause: unknown): boolean {
  return (
    typeof cause === "object" &&
    cause !== null &&
    "code" in cause &&
    (cause as { code: unknown }).code === -1
  );
}

/** Pull a readable message out of whatever the kit threw. */
export function walletErrorMessage(cause: unknown): string {
  if (
    typeof cause === "object" &&
    cause !== null &&
    "message" in cause &&
    typeof (cause as { message: unknown }).message === "string"
  ) {
    return (cause as { message: string }).message;
  }
  return cause instanceof Error ? cause.message : String(cause);
}

/**
 * Sign one Soroban authorisation entry with the connected wallet.
 *
 * This is the whole of what an x402 payment asks of the wallet. The payment is
 * a USDC `transfer` whose network fee the facilitator sponsors, so the buyer
 * never signs or submits a transaction envelope, only the auth entry that says
 * "this account agrees to this transfer". The shape matches SEP-43, which is
 * what `@x402/stellar` expects of a signer.
 */
export async function signAuthEntry(
  authEntry: string,
  opts: { address: string; networkPassphrase?: string },
): Promise<{ signedAuthEntry: string; signerAddress?: string }> {
  const { StellarWalletsKit } = await loadKit();
  return StellarWalletsKit.signAuthEntry(authEntry, {
    address: opts.address,
    networkPassphrase: opts.networkPassphrase ?? NETWORK_PASSPHRASE,
  });
}

/**
 * Sign a plain message with the connected wallet (SEP-43 `signMessage`).
 *
 * Sterish's ownership proof (api-spec §3.7) is SEP-53: ed25519 over
 * `sha256("Stellar Signed Message:
" + message)`, base64. That prefixing and
 * hashing is the wallet's job, which is why the message goes out exactly as the
 * API returned it and nothing is pre-hashed here.
 */
export async function signMessage(
  message: string,
  opts: { address: string; networkPassphrase?: string },
): Promise<string> {
  const { StellarWalletsKit } = await loadKit();
  const { signedMessage } = await StellarWalletsKit.signMessage(message, {
    address: opts.address,
    networkPassphrase: opts.networkPassphrase ?? NETWORK_PASSPHRASE,
  });
  return signedMessage;
}

/**
 * Sign a whole transaction envelope with the connected wallet.
 *
 * Only the testnet setup uses this, to add a USDC trustline. The x402 payment
 * itself never asks for an envelope signature: see `signAuthEntry`.
 */
export async function signTransaction(
  xdr: string,
  opts: { address: string; networkPassphrase?: string },
): Promise<string> {
  const { StellarWalletsKit } = await loadKit();
  const { signedTxXdr } = await StellarWalletsKit.signTransaction(xdr, {
    address: opts.address,
    networkPassphrase: opts.networkPassphrase ?? NETWORK_PASSPHRASE,
  });
  return signedTxXdr;
}
