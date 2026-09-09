import {
  QueryClient,
  defaultShouldDehydrateQuery,
  isServer,
} from "@tanstack/react-query";

/**
 * How long a registry page stays fresh.
 *
 * Sixty seconds, which is exactly what api-spec section 6 permits for a
 * version record, and no longer. The spec allows it because a version record
 * is immutable except through a re-audit, which emits `verdict_flipped`. This
 * is the one place a cache is honest, and it earns its keep: GET /skills takes
 * about ten seconds a page, so paging back and forth without it means waiting
 * ten seconds to see rows the browser already had.
 */
const STALE_MS = 60_000;

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: STALE_MS,
        // The API is slow, not flaky. Retrying a 502 three times turns a ten
        // second failure into a forty second one, and the error state is more
        // useful than a spinner that eventually gives up anyway.
        retry: 1,
        refetchOnWindowFocus: false,
      },
      dehydrate: {
        // Ship queries that are still loading on the server too, so the client
        // picks up a read already in flight rather than starting a second one.
        shouldDehydrateQuery: (query) =>
          defaultShouldDehydrateQuery(query) || query.state.status === "pending",
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined;

/**
 * A fresh client per request on the server, one shared client in the browser.
 *
 * Sharing one on the server would leak one visitor's cached reads into another
 * visitor's render. Making a new one on every browser render would throw the
 * cache away on each suspend, which is the whole thing we are building.
 */
export function getQueryClient(): QueryClient {
  if (isServer) return makeQueryClient();
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}

/** One place decides the key shape, so server prefetch and client read agree. */
export const queryKeys = {
  skills: (start: number, limit: number) =>
    ["skills", { start, limit }] as const,
};
