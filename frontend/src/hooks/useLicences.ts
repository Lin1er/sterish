"use client";

import { useQueries, useQuery } from "@tanstack/react-query";

import { checkVersion } from "@/lib/api";
import { isAccountAddress, readLicences, type Licence } from "@/lib/tokens";

/**
 * Every licence an address holds, read from the tokens contract.
 *
 * Not retried: a failed chain read has to surface as "could not read" rather
 * than sit behind a silent retry, because the alternative a visitor would
 * otherwise infer is "holds nothing".
 */
export function useLicences(address: string) {
  return useQuery({
    queryKey: ["licences", address],
    queryFn: () => readLicences(address),
    enabled: isAccountAddress(address),
    retry: false,
  });
}

/**
 * The current verdict of each licensed version, one chain read per version.
 *
 * Read per version on purpose. A licence says what was bought; the verdict can
 * have changed since, and that change is the reason this page exists.
 */
export function useLicenceVerdicts(licences: Licence[]) {
  return useQueries({
    queries: licences.map((licence) => ({
      queryKey: ["check", licence.skillId, licence.version],
      queryFn: () => checkVersion(licence.skillId, licence.version),
      retry: false,
    })),
  });
}
