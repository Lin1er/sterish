/**
 * Proving to the API that this wallet is the address holding a licence.
 *
 * Who holds a licence is public: `license_minted` events, the tokens contract,
 * and this dashboard's own `/licences/[address]` page. So since STE-48 the free
 * paths of `GET /use` refuse an address alone and ask for a signature over a
 * single-use challenge (api-spec §3.7):
 *
 *   1. `GET` the `challenge_url` the 401 carried,
 *   2. sign `message` exactly as returned, with the wallet's SEP-43
 *      `signMessage` (which is SEP-53: ed25519 over the prefixed sha256),
 *   3. repeat the request with the nonce and the signature.
 *
 * A nonce is bound to one agent, one skill and one version, and is consumed by
 * the first request that proves with it, so a proof is built immediately before
 * the request it is for and never cached.
 */

import {
  ApiError,
  getOwnershipChallenge,
  requestSkill,
  type UseOutcome,
} from "./api";
import type { OwnershipChallenge } from "./types";
import { signMessage, walletErrorMessage } from "./wallet";

/** SEP-53 signatures are 64 raw bytes, base64 encoded. */
export function isValidSignature(value: string): boolean {
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(value)) return false;
  try {
    return atob(value).length === 64;
  } catch {
    return false;
  }
}

/** The proof headers `requestSkill` sends, kept together so neither goes alone. */
export interface OwnershipProof {
  nonce: string;
  signature: string;
}

/**
 * Whether a challenge still has time on it, with a small margin for the round
 * trip. The API clamps its own TTL to at least 30 seconds.
 */
export function isChallengeUsable(
  challenge: OwnershipChallenge,
  now: number = Date.now() / 1000,
): boolean {
  return challenge.expires_at - now > 5;
}

/**
 * Ask for a challenge and have the wallet sign it.
 *
 * The scheme is checked rather than assumed: if the API ever asks for something
 * other than SEP-53, a wallet's `signMessage` would produce a signature in the
 * wrong shape, and sending it would look like tampering rather than an
 * unsupported client.
 */
export async function proveOwnership(
  challengeUrl: string,
  address: string,
): Promise<OwnershipProof> {
  const challenge = await getOwnershipChallenge(challengeUrl);

  if (challenge.agent !== address) {
    throw new Error(
      `The challenge was issued for ${challenge.agent}, not for the connected wallet`,
    );
  }
  if (challenge.signature_scheme !== "SEP-53") {
    throw new Error(
      `This dashboard signs SEP-53 challenges; the API asked for ${challenge.signature_scheme}`,
    );
  }
  if (!isChallengeUsable(challenge)) {
    throw new Error("The challenge expired before it could be signed");
  }

  const signature = await signMessage(challenge.message, { address });
  if (!isValidSignature(signature)) {
    throw new Error(
      "The wallet returned a signature this dashboard cannot use: SEP-53 expects 64 bytes, base64 encoded",
    );
  }
  return { nonce: challenge.nonce, signature };
}

/**
 * Ask for a skill, and prove ownership if the API asks for it.
 *
 * The 401 is not an error to show: it is the API saying "sign this first". The
 * proof is fetched and signed on the spot, then the same request is repeated,
 * so the nonce is used within seconds of being issued. `onProving` lets the UI
 * say that a wallet prompt is coming, since the wallet opens in the middle of
 * what looked like one click.
 *
 * Shared by the version card and the licences page: both hand over a skill
 * somebody already holds, and both must ask for exactly one signature.
 */
export async function requestSkillProving(
  skillId: string,
  version: string,
  opts: { agent: string; payment?: string; onProving?: () => void },
): Promise<UseOutcome> {
  try {
    return await requestSkill(skillId, version, {
      agent: opts.agent,
      payment: opts.payment,
    });
  } catch (cause) {
    const needsProof =
      cause instanceof ApiError &&
      cause.status === 401 &&
      cause.challengeUrl !== null;
    if (!needsProof) throw cause;

    opts.onProving?.();
    const proof = await proveOwnership(
      (cause as ApiError).challengeUrl as string,
      opts.agent,
    );
    return await requestSkill(skillId, version, {
      agent: opts.agent,
      payment: opts.payment,
      proof,
    });
  }
}

/** Why a proof did not happen, in terms the card can word. */
export type ProofFailure = {
  kind: "declined" | "wallet_unavailable" | "expired" | "failed";
  message: string;
};

/** What to tell somebody when a proof did not work out. */
export function describeProofFailure(cause: unknown): ProofFailure {
  if (cause instanceof ApiError) {
    if (cause.code === "INVALID_OWNERSHIP_PROOF") {
      return {
        kind: "expired",
        message: `The API refused the proof (${cause.detail}). A challenge is single use and short lived, so try again to sign a fresh one.`,
      };
    }
    return {
      kind: "failed",
      message: `${cause.message}${cause.code ? ` (${cause.code})` : ""}`,
    };
  }

  // Wallets reject with a plain object, not an Error, so its message has to be
  // dug out rather than stringified: String({...}) is "[object Object]", which
  // is what the licences page showed for a declined signature.
  const message = walletErrorMessage(cause);
  if (
    /not connected|not installed|not available|no wallet|locked/i.test(message)
  ) {
    return {
      kind: "wallet_unavailable",
      message:
        "Your wallet did not respond. Make sure it is installed, unlocked and connected to this site, then try again.",
    };
  }
  if (/reject|declin|denied|cancel/i.test(message)) {
    return {
      kind: "declined",
      message:
        "You declined the signature. It proves this wallet holds the licence; it is not a payment and costs nothing.",
    };
  }
  return {
    kind: "failed",
    message:
      message === "[object Object]"
        ? "The wallet returned an error without saying why. Nothing was charged."
        : message,
  };
}
