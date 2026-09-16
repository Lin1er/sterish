"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addUsdcTrustline,
  fundWithFriendbot,
  readAccountSetup,
  usdcAssetFor,
} from "@/lib/testnetSetup";

/**
 * Where a wallet stands on the way to paying, and the two steps the dashboard
 * can take for it (Friendbot and the USDC trustline).
 *
 * The account read is not cached across a step: each mutation invalidates it,
 * so the checklist moves on only once Horizon says the step really happened.
 */
export function useTestnetSetup(
  address: string,
  asset: string,
  enabled: boolean,
) {
  const queryClient = useQueryClient();
  const key = ["testnet-setup", address] as const;

  const setup = useQuery({
    queryKey: key,
    queryFn: () => readAccountSetup(address),
    enabled,
    staleTime: 0,
    retry: false,
  });

  const usdc = useQuery({
    queryKey: ["testnet-usdc-asset", asset],
    queryFn: () => usdcAssetFor({ asset }),
    enabled,
    staleTime: Infinity,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: key });

  const fund = useMutation({
    mutationFn: () => fundWithFriendbot(address),
    onSettled: refresh,
  });

  const trust = useMutation({
    mutationFn: () => addUsdcTrustline(address),
    onSettled: refresh,
  });

  return { setup, usdc, fund, trust, refresh };
}
