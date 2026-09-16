"use client";

import { useQuery } from "@tanstack/react-query";

import { getLicense } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";

/**
 * Whether the connected wallet holds a licence for one exact version.
 *
 * Per version, never per skill: a licence is minted for `(skill_id, version)`
 * and a licence for 1.0.0 says nothing about 1.1.0. Disabled until there is an
 * address to ask about, because an anonymous visitor has no licence status at
 * all, which is different from holding none.
 *
 * Not retried. `GET /license` answers a failed chain read with a 502, and that
 * has to show up as "could not tell" promptly rather than after a silent retry,
 * so it is never mistaken for `held: false`.
 */
export function useLicense(
  skillId: string,
  version: string,
  agent: string | null,
) {
  return useQuery({
    queryKey: queryKeys.licence(skillId, version, agent ?? ""),
    queryFn: () => getLicense(skillId, version, agent as string),
    enabled: agent !== null,
    retry: false,
  });
}
