"use client";

import { useQueries, useQuery } from "@tanstack/react-query";

import { checkVersion, listLicenses } from "@/lib/api";
import type { LicenseRecord } from "@/lib/types";
import { isAccountAddress } from "@/utils/stellar";

/**
 * Every licence an address holds, from `GET /licenses` (spec §3.10).
 *
 * STE-47 read the tokens contract from the browser, id by id, because the API
 * had no list. STE-46 gave it one, built from the contract's own enumeration
 * rather than from events, so a licence older than the RPC event window is
 * still listed. A failed chain read there is a 502, never a shorter list.
 *
 * Not retried: "could not read" has to surface promptly, because the wrong
 * conclusion to draw from a slow failure is "this address holds nothing".
 */
export function useLicences(address: string) {
  return useQuery({
    queryKey: ["licences", address],
    queryFn: () => listLicenses(address),
    enabled: isAccountAddress(address),
    retry: false,
  });
}

/**
 * The current verdict of each licensed version, one read per version.
 *
 * Deliberately separate: `/licenses` joins in no verdict, and that is the
 * point. A licence says what was bought; the verdict can have changed since,
 * and that change is the reason this page exists.
 */
export function useLicenceVerdicts(licences: LicenseRecord[]) {
  return useQueries({
    queries: licences.map((licence) => ({
      queryKey: ["check", licence.skill_id, licence.version],
      queryFn: () => checkVersion(licence.skill_id, licence.version),
      retry: false,
    })),
  });
}
