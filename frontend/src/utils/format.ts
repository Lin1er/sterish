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

/**
 * "4 minutes ago". Falls back to the absolute UTC time past a week, because
 * "23 days ago" is harder to check against an explorer than a date.
 */
export function formatRelativeTime(seconds: number): string {
  const delta = Math.floor(Date.now() / 1000) - seconds;
  if (delta < 60) return "just now";
  if (delta < 3600) {
    const minutes = Math.floor(delta / 60);
    return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  }
  if (delta < 86_400) {
    const hours = Math.floor(delta / 3600);
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  if (delta < 604_800) {
    const days = Math.floor(delta / 86_400);
    return `${days} day${days === 1 ? "" : "s"} ago`;
  }
  return formatLedgerTime(seconds).slice(0, 10);
}
