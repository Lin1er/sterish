"use client";

import {
  Check,
  CircleDashed,
  Copy,
  ExternalLink,
  Loader2,
  RotateCcw,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useTestnetSetup } from "@/hooks/useTestnetSetup";
import { USDC_FAUCET_URL, decimalToBaseUnits } from "@/lib/testnetSetup";
import type { PaymentRequirement } from "@/lib/types";
import { EXPLORER_BASE, walletErrorMessage } from "@/lib/wallet";
import { formatBaseUnits } from "@/lib/x402";

/**
 * Three steps from a brand new testnet wallet to one that can pay, shown where
 * the buyer found out they cannot pay yet: under the price.
 *
 * Each step reads its state from Horizon rather than remembering that a button
 * was clicked, so a wallet set up somewhere else shows as done, and a step that
 * silently failed does not show as done.
 */

type StepState = "done" | "todo" | "blocked";

function Step({
  n,
  state,
  title,
  detail,
  children,
}: {
  n: number;
  state: StepState;
  title: string;
  detail?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <li className="flex gap-3 py-3 first:pt-0 last:pb-0">
      <span
        className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border text-xs ${
          state === "done"
            ? "border-safe-border bg-safe-surface text-safe"
            : state === "todo"
              ? "border-hairline-strong text-text"
              : "border-border text-text-tertiary"
        }`}
        aria-hidden
      >
        {state === "done" ? <Check className="size-3.5" /> : n}
      </span>
      <div className="min-w-0 flex-1">
        <p
          className={`text-sm ${state === "blocked" ? "text-text-tertiary" : "text-text"}`}
        >
          {title}
          <span className="sr-only">
            {state === "done"
              ? " (done)"
              : state === "blocked"
                ? " (waiting on the step before)"
                : ""}
          </span>
        </p>
        {detail ? (
          <div className="mt-1 text-xs text-text-secondary">{detail}</div>
        ) : null}
        {children ? (
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            {children}
          </div>
        ) : null}
      </div>
    </li>
  );
}

/** A wallet that said no, or is not there, is not an error in this guide's voice. */
function signingMessage(cause: unknown): string {
  const message = walletErrorMessage(cause);
  if (
    /not connected|not installed|not available|no wallet|locked/i.test(message)
  ) {
    return "Your wallet did not respond. Make sure it is installed, unlocked and connected to this site.";
  }
  if (/reject|declin|denied|cancel/i.test(message)) {
    return "You declined the trustline in your wallet. Nothing was changed.";
  }
  return message;
}

export function TestnetSetup({
  address,
  requirement,
  onReady,
}: {
  address: string;
  requirement: PaymentRequirement;
  /** Called when every step reads as done, to re-read the balance above. */
  onReady: () => void;
}) {
  const { setup, usdc, fund, trust, refresh } = useTestnetSetup(
    address,
    requirement.asset,
    true,
  );
  const [copied, setCopied] = useState(false);

  const account = setup.data;
  const funded = account?.funded ?? false;
  const trusted = account?.trustline ?? false;
  const enough =
    account?.usdc != null &&
    decimalToBaseUnits(account.usdc) >= BigInt(requirement.amount);
  const ready = funded && trusted && enough;

  // Once Horizon says the wallet can pay, the quote above is re-read once, so
  // the Pay button unlocks without the buyer having to find a refresh.
  const reported = useRef(false);
  useEffect(() => {
    if (ready && !reported.current) {
      reported.current = true;
      onReady();
    }
  }, [ready, onReady]);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  if (setup.isPending) {
    return (
      <p className="mt-4 inline-flex items-center gap-2 text-xs text-text-secondary">
        <Loader2 className="size-3.5 animate-spin" aria-hidden />
        Checking whether this wallet is ready to pay...
      </p>
    );
  }

  if (setup.error) {
    return (
      <p className="mt-4 text-xs text-warning">
        Could not read this account from Horizon, so the setup steps cannot be
        shown. {setup.error.message}
      </p>
    );
  }

  const price = formatBaseUnits(requirement.amount);

  return (
    <div className="mt-5 border-t border-border pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-bold">
          {ready
            ? "This wallet is ready to pay"
            : "Get this wallet ready to pay"}
        </p>
        <p className="text-xs text-text-tertiary">
          Testnet only. Nothing here costs real money.
        </p>
      </div>

      <ol className="mt-3 divide-y divide-border">
        <Step
          n={1}
          state={funded ? "done" : "todo"}
          title="Activate the account with testnet XLM"
          detail={
            funded
              ? `Active, holding ${Number(account?.xlm ?? 0).toLocaleString("en-US")} XLM.`
              : "A new Stellar account does not exist until it holds XLM. Friendbot sends free testnet XLM. The payment itself spends none: its fee is sponsored."
          }
        >
          {funded ? null : (
            <Button
              size="sm"
              onClick={() => fund.mutate()}
              disabled={fund.isPending}
            >
              {fund.isPending ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : null}
              Fund with Friendbot
            </Button>
          )}
          {fund.error ? (
            <span className="text-xs text-danger">{fund.error.message}</span>
          ) : null}
        </Step>

        <Step
          n={2}
          state={trusted ? "done" : funded ? "todo" : "blocked"}
          title="Trust Circle's testnet USDC"
          detail={
            trusted
              ? "Trustline added."
              : usdc.data === null
                ? "The API charges in an asset this guide does not recognise, so no trustline is offered. Add it in your wallet by hand."
                : "An account can only hold an asset it trusts. Your wallet signs one transaction adding USDC from Circle's issuer, the exact asset the price above is in."
          }
        >
          {trusted || !funded || usdc.data === null ? null : (
            <Button
              size="sm"
              onClick={() => trust.mutate()}
              disabled={trust.isPending || usdc.isPending}
            >
              {trust.isPending ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : null}
              {trust.isPending
                ? "Approve in your wallet..."
                : "Add USDC trustline"}
            </Button>
          )}
          {trust.data ? (
            <a
              href={`${EXPLORER_BASE}/tx/${trust.data}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-keyword hover:underline"
            >
              Trustline transaction
              <ExternalLink className="size-3" aria-hidden />
            </a>
          ) : null}
          {trust.error ? (
            <span className="text-xs text-danger">
              {signingMessage(trust.error)}
            </span>
          ) : null}
        </Step>

        <Step
          n={3}
          state={enough ? "done" : trusted ? "todo" : "blocked"}
          title={`Get at least ${price} testnet USDC`}
          detail={
            enough ? (
              `Holding ${formatBaseUnits(decimalToBaseUnits(account?.usdc ?? "0"))} USDC.`
            ) : (
              <>
                Circle&apos;s faucet sends free testnet USDC. Choose{" "}
                <span className="text-text">Stellar Testnet</span>, paste your
                address, and come back here. It sits behind a captcha, so this
                step cannot be done for you.
              </>
            )
          }
        >
          {enough || !trusted ? null : (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  void navigator.clipboard
                    .writeText(address)
                    .then(() => setCopied(true))
                    .catch(() => {});
                }}
              >
                {copied ? (
                  <Check data-icon="inline-start" />
                ) : (
                  <Copy data-icon="inline-start" />
                )}
                {copied ? "Address copied" : "Copy my address"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                render={
                  <a
                    href={USDC_FAUCET_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                  />
                }
                nativeButton={false}
              >
                <ExternalLink data-icon="inline-start" />
                Open Circle faucet
              </Button>
            </>
          )}
        </Step>
      </ol>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => void refresh()}
          disabled={setup.isFetching}
        >
          {setup.isFetching ? (
            <Loader2 data-icon="inline-start" className="animate-spin" />
          ) : (
            <RotateCcw data-icon="inline-start" />
          )}
          Check again
        </Button>
        {!ready ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-text-tertiary">
            <CircleDashed className="size-3.5" aria-hidden />
            Steps update from the ledger, not from what was clicked
          </span>
        ) : null}
      </div>
    </div>
  );
}
