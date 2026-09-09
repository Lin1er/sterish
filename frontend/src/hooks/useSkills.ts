"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { listSkills } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";

/**
 * One page of the registry.
 *
 * `keepPreviousData` matters more here than it usually would: GET /skills takes
 * about ten seconds, so without it every page change would blank the table for
 * ten seconds. With it the previous rows stay on screen, marked as stale, until
 * the new ones arrive, and a page already visited comes back instantly.
 */
export function useSkills(start: number, limit: number) {
  return useQuery({
    queryKey: queryKeys.skills(start, limit),
    queryFn: () => listSkills({ start, limit }),
    placeholderData: keepPreviousData,
  });
}
