"use client";

import { useQuery } from "@tanstack/react-query";

import { getFeed } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { FeedEvent } from "@/lib/types";

/**
 * The whole feed is pulled and filtered here because `GET /feed` takes only
 * `limit` and `offset`: there is no `skill_id` parameter. At 142 indexed
 * events that is one request and cheap, but it does not scale, and the fix
 * belongs in the API rather than in a bigger limit here. Raised with James.
 */
const TRAIL_SCAN_LIMIT = 200;

/**
 * Every indexed event for one skill, newest first.
 *
 * This is the audit trail: registration, each version published, and each
 * verdict written, with the transaction behind every line. It is deliberately
 * separate from the version cards above it, which read the chain. The trail
 * says what happened and when; the chain says what is true now.
 */
export function useSkillTrail(skillId: string) {
  return useQuery({
    queryKey: queryKeys.feed(TRAIL_SCAN_LIMIT),
    queryFn: () => getFeed({ limit: TRAIL_SCAN_LIMIT }),
    select: (data): FeedEvent[] =>
      data.events.filter((event) => event.skill_id === skillId),
  });
}
