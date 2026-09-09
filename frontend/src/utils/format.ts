/**
 * Pure formatting helpers. No state, no chain, no fetch.
 */

/** `GABC...WXYZ`, the form every Stellar explorer and wallet uses. */
export function shortAddress(address: string): string {
  if (address.length <= 12) return address;
  return `${address.slice(0, 4)}...${address.slice(-4)}`;
}

/**
 * A ledger timestamp as `YYYY-MM-DD hh:mm:ss` in UTC.
 *
 * UTC on purpose, not the viewer's locale: these are ledger times, and two
 * people comparing an audit against stellar.expert must read the same number.
 */
export function formatLedgerTime(seconds: number): string {
  return new Date(seconds * 1000).toISOString().replace("T", " ").slice(0, 19);
}

/** A 64-character hash shortened for display, both ends kept. */
export function shortHash(hash: string, chars = 10): string {
  if (hash.length <= chars * 2) return hash;
  return `${hash.slice(0, chars)}...${hash.slice(-chars)}`;
}
