"use client";

import { useQuery } from "@tanstack/react-query";

import { getFeed } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";

/**
 * How often the feed asks for new activity.
 *
 * Fifteen seconds. Stellar testnet closes a ledger about every five, and an
 * audit is a human-and-pipeline event that arrives in minutes, not seconds, so
 * polling faster would only add load for the appearance of liveness. Slower
 * than this and a reviewer running the pipeline during a demo would sit
 * wondering whether the page is broken.
 */
export const FEED_REFETCH_MS = 15_000;

/**
 * Recent registry activity.
 *
 * Unlike the registry table this really does want to refetch on focus: coming
 * back to the tab is exactly the moment somebody wants to know what happened
 * while they were away.
 */
export function useFeed(limit: number) {
  return useQuery({
    queryKey: queryKeys.feed(limit),
    queryFn: () => getFeed({ limit }),
    refetchInterval: FEED_REFETCH_MS,
    refetchOnWindowFocus: true,
    // The feed is a cache by definition, so there is no point holding it fresh
    // for the 60s a verdict record gets.
    staleTime: 0,
  });
}
