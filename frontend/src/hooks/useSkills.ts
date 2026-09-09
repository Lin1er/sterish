"use client";

import { useQuery } from "@tanstack/react-query";

import { listSkills } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";

/**
 * One page of the registry.
 *
 * Deliberately without `keepPreviousData`. Holding the previous page on screen
 * while the next one loads sounds kind, but at ten seconds a table full of the
 * wrong rows, dimmed, is read as a broken table rather than a loading one. It
 * needed a sentence of explanation above it to be understandable at all, which
 * is the tell that the pattern was wrong here. A skeleton says "loading"
 * without anybody having to be told.
 *
 * A page that has been visited still returns instantly, from the cache.
 */
export function useSkills(start: number, limit: number) {
  return useQuery({
    queryKey: queryKeys.skills(start, limit),
    queryFn: () => listSkills({ start, limit }),
  });
}
