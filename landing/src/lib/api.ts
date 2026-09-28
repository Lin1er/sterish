import type { SkillList, VersionCheck } from "./types";

/**
 * The two reads this page makes, and nothing else.
 *
 * The dashboard's client is 391 lines because it also builds x402 payments,
 * decodes settlement receipts and talks to a wallet. None of that belongs in a
 * marketing page, and copying it across would mean carrying payment code on a
 * deployment that can never take a payment. Two endpoints, one error shape.
 */

/**
 * Absolute on purpose: these calls run in server components, where a relative
 * path has no origin to resolve against.
 */
export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "https://api.sterish.xyz"
).replace(/\/+$/, "");

/**
 * Shorter than the dashboard's 30s. There, a slow read still has to resolve
 * because someone is waiting on a verdict before installing. Here the caller
 * falls back to a dated snapshot and says so, and a landing page that hangs
 * for half a minute has already lost the reader — so it gives up sooner and
 * shows something true instead.
 */
const TIMEOUT_MS = 10_000;

async function get<T>(path: string): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const response = await fetch(url, {
    // Not cached, matching the dashboard: api-spec §4 is explicit that a stale
    // or invented verdict is the worst thing this product can serve. The page
    // handles freshness itself, by streaming and by labelling its own as-of
    // date.
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_MS),
    headers: { accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`GET ${url} answered ${response.status}`);
  }
  return (await response.json()) as T;
}

/** Spec §3.4. `limit` is clamped to 100 by the API. */
export function listSkills(
  params: { start?: number; limit?: number } = {},
): Promise<SkillList> {
  const query = new URLSearchParams({
    start: String(params.start ?? 0),
    limit: String(params.limit ?? 20),
  });
  return get<SkillList>(`/skills?${query}`);
}

/** Spec §3.2. Resolved by name; used here for display, never as a gate. */
export function checkVersion(
  skillId: string,
  version: string,
): Promise<VersionCheck> {
  return get<VersionCheck>(
    `/check/${encodeURIComponent(skillId)}/${encodeURIComponent(version)}`,
  );
}
