"use client";

import { LogOut, Wallet } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useWallet } from "@/hooks/useWallet";
import { shortAddress } from "@/utils/format";

/**
 * The header's wallet control.
 *
 * The connected address is the agent identity for the x402 buy flow in STE-22,
 * so it is shown in full on hover and in the accessible name, not only as the
 * truncated form. Somebody checking that they paid from the right account needs
 * to be able to read the whole thing.
 *
 * On a phone the labels shrink but the address never does: it is the one piece
 * of information here, and the words around it are not.
 */
export function WalletButton() {
  const { status, address, error, connect, disconnect } = useWallet();

  // The session lives in localStorage, which the server cannot read, so the
  // first paint is a placeholder of the same size on both sides. Anything else
  // is a hydration mismatch or a visible flash of the wrong state.
  if (status === "restoring") {
    return <Skeleton className="h-8 w-28 sm:w-32" aria-hidden />;
  }

  if (status === "connected" && address) {
    return (
      <div className="flex items-center gap-1.5 sm:gap-2">
        <span
          className="numeric rounded-lg border border-border bg-surface px-2 py-1 font-mono text-xs whitespace-nowrap text-text"
          title={address}
        >
          {shortAddress(address)}
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void disconnect()}
          aria-label={`Disconnect wallet ${address}`}
        >
          <LogOut data-icon="inline-start" />
          {/* The word is dropped on a phone, not the control. The icon plus the
              accessible name still say what it does. */}
          <span className="hidden sm:inline">Disconnect</span>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {error ? (
        <span
          role="alert"
          className="hidden max-w-56 truncate text-xs text-danger sm:inline"
        >
          {error}
        </span>
      ) : null}
      <Button
        onClick={() => void connect()}
        disabled={status === "connecting"}
        aria-busy={status === "connecting"}
        className="whitespace-nowrap"
      >
        <Wallet data-icon="inline-start" />
        {status === "connecting" ? (
          "Connecting..."
        ) : (
          <>
            Connect<span className="hidden sm:inline">&nbsp;wallet</span>
          </>
        )}
      </Button>
    </div>
  );
}
