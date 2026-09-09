"use client";

import { useQuery } from "@tanstack/react-query";

import { getFeed } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { FeedEvent } from "@/lib/types";

import { FEED_SCAN_LIMIT } from "./useFeed";

/**
 * Every indexed event for one skill, newest first.
 *
 * The whole feed is pulled and filtered here because `GET /feed` takes only
 * `limit` and `offset`: there is no `skill_id` parameter. That is affordable
 * because the feed is an index read costing about 0.2s, and it shares one
 * cache entry with the audit feed page. It stops being affordable past the
 * 200-event cap, and the fix then belongs in the API, not in a bigger limit.
 *
 * This is the audit trail: registration, each version published, and each
 * verdict written, with the transaction behind every line. It is deliberately
 * separate from the version cards above it, which read the chain. The trail
 * says what happened and when; the chain says what is true now.
 */
export function useSkillTrail(skillId: string) {
  return useQuery({
    queryKey: queryKeys.feed(FEED_SCAN_LIMIT),
    queryFn: () => getFeed({ limit: FEED_SCAN_LIMIT }),
    select: (data): FeedEvent[] =>
      data.events.filter((event) => event.skill_id === skillId),
  });
}
