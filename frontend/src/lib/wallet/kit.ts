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

/** `GABC…WXYZ`, the form every Stellar explorer and wallet uses. */
export function truncateAddress(address: string): string {
  if (address.length <= 12) return address;
  return `${address.slice(0, 4)}...${address.slice(-4)}`;
}
