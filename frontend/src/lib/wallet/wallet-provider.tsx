"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { isUserCancelled, loadKit, walletErrorMessage } from "./kit";

/**
 * `restoring` exists so the header can avoid flashing "Connect wallet" at
 * somebody who is already connected. The kit keeps the session in localStorage,
 * which the server cannot see, so the first render on both sides is
 * deliberately identical and neutral, and the real state arrives after mount.
 * Rendering the address during SSR instead would be a hydration mismatch.
 */
export type WalletStatus =
  | "restoring"
  | "disconnected"
  | "connecting"
  | "connected";

export interface WalletState {
  status: WalletStatus;
  address: string | null;
  /** Null unless the last connect attempt actually failed. A cancel is not a failure. */
  error: string | null;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
}

const WalletContext = createContext<WalletState | null>(null);

export function WalletProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<WalletStatus>("restoring");
  const [address, setAddress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Restore. The kit's STATE_UPDATED event also fires once at launch with
  // whatever it read from localStorage, so subscribing is both the restore
  // path and the ongoing-updates path. getAddress() would work too, but it
  // throws when nothing is stored, which turns "not connected yet" into an
  // exception on every first visit.
  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    let cancelled = false;

    loadKit()
      .then(({ StellarWalletsKit, KitEventType }) => {
        if (cancelled) return;
        unsubscribe = StellarWalletsKit.on(
          KitEventType.STATE_UPDATED,
          (event) => {
            const next = event.payload.address ?? null;
            setAddress(next);
            // Never downgrade the status while a connect is mid-flight: the
            // event fires with no address at that moment and would otherwise
            // flip the button back to "Connect" under the open modal.
            setStatus((current) =>
              current === "connecting" && !next
                ? current
                : next
                  ? "connected"
                  : "disconnected",
            );
          },
        );
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setStatus("disconnected");
        setError(walletErrorMessage(cause));
      });

    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

  const connect = useCallback(async () => {
    setError(null);
    setStatus("connecting");
    try {
      const { StellarWalletsKit } = await loadKit();
      // authModal picks the wallet, sets it as the active module, and asks it
      // for the public key. Its promise resolves with that address.
      const { address: connected } = await StellarWalletsKit.authModal();
      setAddress(connected);
      setStatus("connected");
    } catch (cause) {
      // Closing the picker rejects with { code: -1 }. That is a decision, not
      // an error, so it leaves no banner behind.
      if (!isUserCancelled(cause)) {
        setError(walletErrorMessage(cause));
      }
      setStatus(address ? "connected" : "disconnected");
    }
  }, [address]);

  const disconnect = useCallback(async () => {
    setError(null);
    try {
      const { StellarWalletsKit } = await loadKit();
      await StellarWalletsKit.disconnect();
    } catch (cause) {
      setError(walletErrorMessage(cause));
    } finally {
      // Clear locally whatever the kit reported: a disconnect that half fails
      // must not leave the header claiming a live session.
      setAddress(null);
      setStatus("disconnected");
    }
  }, []);

  const value = useMemo<WalletState>(
    () => ({ status, address, error, connect, disconnect }),
    [status, address, error, connect, disconnect],
  );

  return (
    <WalletContext.Provider value={value}>{children}</WalletContext.Provider>
  );
}

export function useWallet(): WalletState {
  const context = useContext(WalletContext);
  if (!context) {
    throw new Error("useWallet must be used inside <WalletProvider>");
  }
  return context;
}
