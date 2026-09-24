/**
 * Stellar address shapes, as text. No network, no SDK: a 56 character `G...`
 * is the only thing that can hold a licence, and both the licences page and
 * its route check that before asking the API.
 */

/** A classic ed25519 account. Contract (`C...`) and muxed (`M...`) are not. */
export function isAccountAddress(value: string): boolean {
  return /^G[A-Z2-7]{55}$/.test(value);
}
