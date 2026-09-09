"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { WalletProvider } from "@/hooks/useWallet";
import { getQueryClient } from "@/lib/queryClient";

/**
 * Where the client-side providers are assembled. One place to add the next
 * one, and the only reason the root layout needs a client boundary at all.
 */
export function Providers({ children }: { children: ReactNode }) {
  // Not useState: getQueryClient already keeps one instance per browser and a
  // fresh one per server render, which is the property that matters.
  const queryClient = getQueryClient();

  return (
    <QueryClientProvider client={queryClient}>
      <WalletProvider>{children}</WalletProvider>
    </QueryClientProvider>
  );
}
