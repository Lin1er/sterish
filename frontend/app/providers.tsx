"use client";

import type { ReactNode } from "react";

import { WalletProvider } from "@/hooks/useWallet";

/**
 * Where the client-side providers are assembled. One place to add the next
 * one, and the only reason the root layout needs a client boundary at all.
 */
export function Providers({ children }: { children: ReactNode }) {
  return <WalletProvider>{children}</WalletProvider>;
}
