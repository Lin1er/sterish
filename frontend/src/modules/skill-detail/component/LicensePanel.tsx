"use client";

import {
  AlertOctagon,
  Download,
  ExternalLink,
  KeyRound,
  Loader2,
  RotateCcw,
  Wallet,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLicense } from "@/hooks/useLicense";
import { usePurchase, type PurchaseState } from "@/hooks/usePurchase";
import { useWallet } from "@/hooks/useWallet";
import { ApiError } from "@/lib/api";
import type { SkillArtifact, Verdict } from "@/lib/types";
import { EXPLORER_BASE } from "@/lib/wallet";
import { formatBaseUnits, type PaymentFailure } from "@/lib/x402";
import { shortAddress, shortHash } from "@/utils/format";

/**
 * Licence status and the buy flow, for one version.
 *
 * Two questions live here and are never merged: "do you hold a licence?" comes
 * from the tokens contract, "is this version SAFE?" comes from the registry.
 * Yes to the first and no to the second is a reachable state (a version
 * re-audited after purchase), and it is the loudest thing this panel can say.
 */

function TxLink({ hash, label }: { hash: string; label: string }) {
  return (
    <a
      href={`${EXPLORER_BASE}/tx/${hash}`}
      target="_blank"
      rel="noopener noreferrer"
      className="numeric inline-flex items-center gap-1 font-mono text-xs text-keyword hover:underline"
      title={hash}
    >
      {label} {shortHash(hash, 8)}
      <ExternalLink className="size-3" aria-hidden />
    </a>
  );
}

function download(skillId: string, version: string, artifact: SkillArtifact) {
  const blob = new Blob([JSON.stringify(artifact, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${skillId}@${version}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

/** What to tell the buyer about a failure, and whether money may have moved. */
function describeFailure(
  error: ApiError | PaymentFailure,
  after: "request" | "signature" | "payment",
): { title: string; body: string } {
  if (!(error instanceof ApiError)) {
    return {
      title:
        error.kind === "declined"
          ? "Payment declined"
          : error.kind === "wallet_unavailable"
            ? "Wallet not available"
            : error.kind === "insufficient_funds"
              ? "Not enough USDC"
              : "The payment could not be prepared",
      body: error.message,
    };
  }

  switch (error.code) {
    case "NOT_VERIFIED":
      return {
        title: "This version cannot be licensed",
        body: "Only a version the registry calls SAFE is ever sold. The tokens contract refuses the mint too, so this does not depend on the API.",
      };
    case "PAYMENT_REJECTED":
      return {
        title: "The payment was refused",
        body: /balance|insufficient|funds/i.test(error.detail)
          ? `The facilitator says this account cannot cover the price (${error.detail}). Add testnet USDC and try again.`
          : `The facilitator refused it: ${error.detail}`,
      };
    case "FACILITATOR_UNAVAILABLE":
      return {
        title: "The payment service is unreachable",
        body:
          after === "payment"
            ? "The purchase did not complete. It failed after your payment was sent, so check the licence status above before paying again."
            : "The purchase could not start. Reading verdicts is unaffected; try again later.",
      };
    case "LICENSE_MINT_PENDING":
      return {
        title: "Paid, licence not minted yet",
        body: "Your payment settled but the mint did not finish. Request the skill again to complete it. You will not be charged a second time.",
      };
    case "PAYMENT_OUTCOME_UNKNOWN":
      return {
        title: "No answer after paying",
        body: "The payment was sent and the API did not answer, so it may have gone through. Check the licence status above before trying again.",
      };
    case "ARTIFACT_NOT_FOUND":
      return {
        title: "The API has no copy of this version",
        body:
          after === "payment"
            ? "The API could not deliver the skill after payment. Your licence may still have been minted, so check the status above before paying again."
            : "There is nothing to deliver, so nothing was offered for sale.",
      };
    case "ARTIFACT_HASH_MISMATCH":
      return {
        title: "The API refused to serve a copy that does not match",
        body: "The files the API holds do not hash to the content hash on chain, so it would not send them. This protects you from paying for one skill and receiving another.",
      };
    default:
      return {
        title: error.isTransport
          ? "Cannot reach the verification API"
          : "The verification API returned an error",
        body: `${error.message}${error.code ? ` (${error.code})` : ""}`,
      };
  }
}

type Tone = "neutral" | "active" | "safe" | "danger";

const TONE: Record<Tone, string> = {
  neutral: "border-border",
  active: "border-border bg-bg-deep/50",
  safe: "border-safe-border bg-safe-surface",
  danger: "border-danger-border bg-danger-surface",
};

/**
 * The licence section is the bottom band of the version card, not a box inside
 * it. It runs to the card's edges (the negative margins cancel the card's p-5)
 * under a single divider, and the state is carried by the band's own tint:
 * darker while a payment is in progress, green once delivered, red on a
 * failure. The earlier version nested a bordered quote inside a bordered panel
 * inside the card, three frames deep for one decision.
 */
function Strip({
  tone = "neutral",
  alert = false,
  children,
}: {
  tone?: Tone;
  alert?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label="Licence"
      role={alert ? "alert" : undefined}
      className={`-mx-5 mt-5 -mb-5 rounded-b-lg border-t px-5 py-4 transition-colors ${TONE[tone]}`}
    >
      {children}
    </section>
  );
}

function toneOf(state: PurchaseState): Tone {
  switch (state.step) {
    case "granted":
      return "safe";
    case "failed":
      return "danger";
    case "quoted":
    case "signing":
    case "settling":
      return "active";
    default:
      return "neutral";
  }
}

function Flow({
  skillId,
  version,
  state,
  onStart,
  onPay,
  onReset,
}: {
  skillId: string;
  version: string;
  state: PurchaseState;
  onStart: () => void;
  onPay: () => void;
  onReset: () => void;
}) {
  switch (state.step) {
    case "idle":
      return null;

    case "requesting":
      return (
        <p className="mt-4 inline-flex items-center gap-2 text-sm text-text-secondary">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Asking the API for {version}...
        </p>
      );

    case "quoted": {
      const { requirement, balance } = state;
      const price = formatBaseUnits(requirement.amount);
      const short =
        typeof balance === "bigint" && balance < BigInt(requirement.amount);
      return (
        <div className="mt-4">
          <p className="text-xs text-text-tertiary">
            402 Payment Required, x402 v{state.paymentRequired.x402Version}
          </p>
          <p className="mt-1 text-lg font-bold">
            <span className="numeric font-mono">{price}</span> USDC
            <span className="ml-2 text-sm font-normal text-text-secondary">
              once, for {version} only
            </span>
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3 text-xs lg:grid-cols-4">
            <div>
              <dt className="text-text-tertiary">Paid to</dt>
              <dd
                className="numeric mt-0.5 font-mono break-all"
                title={requirement.payTo}
              >
                {shortAddress(requirement.payTo)}
              </dd>
            </div>
            <div>
              <dt className="text-text-tertiary">Asset</dt>
              <dd className="mt-0.5">
                <a
                  href={`${EXPLORER_BASE}/contract/${requirement.asset}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="numeric inline-flex items-center gap-1 font-mono text-keyword hover:underline"
                  title={requirement.asset}
                >
                  USDC {shortAddress(requirement.asset)}
                  <ExternalLink className="size-3" aria-hidden />
                </a>
              </dd>
            </div>
            <div>
              <dt className="text-text-tertiary">Network</dt>
              <dd className="numeric mt-0.5 font-mono">
                {requirement.network}
              </dd>
            </div>
            <div>
              <dt className="text-text-tertiary">Your balance</dt>
              <dd
                className={`numeric mt-0.5 font-mono ${short ? "text-danger" : ""}`}
              >
                {balance === undefined
                  ? "reading..."
                  : balance === null
                    ? "unavailable"
                    : `${formatBaseUnits(balance)} USDC`}
              </dd>
            </div>
          </dl>
          {balance === null ? (
            // The SAC refuses to report a balance for an account with no USDC
            // trustline, which is the usual reason this read fails. Signing
            // would fail the same way, so it is said before the wallet opens.
            <p className="mt-4 text-xs text-warning">
              Your USDC balance could not be read. This usually means the
              account has no USDC trustline yet, in which case the payment will
              not go through either.
            </p>
          ) : null}
          {short ? (
            <p className="mt-4 text-sm text-danger">
              This account holds less than {price} USDC. Get testnet USDC from
              the{" "}
              <a
                href="https://faucet.circle.com/"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                Circle faucet
              </a>{" "}
              first.
            </p>
          ) : null}
          <p className="mt-4 max-w-3xl text-xs text-text-secondary">
            Your wallet signs one authorisation for this transfer. The network
            fee is sponsored, so no XLM is spent. The licence is soulbound to
            this account and cannot be transferred.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button onClick={onPay} disabled={short}>
              <Wallet data-icon="inline-start" />
              Pay {price} USDC
            </Button>
            <Button variant="ghost" onClick={onReset}>
              Cancel
            </Button>
          </div>
        </div>
      );
    }

    case "signing":
      return (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <p className="inline-flex items-center gap-2 text-sm text-text">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Approve the payment in your wallet...
          </p>
          {/* A wallet that never answers (closed popup, missing extension)
              would otherwise hold this spinner forever. Cancelling here also
              discards a signature that arrives late, so it is never sent. */}
          <Button variant="ghost" size="sm" onClick={onReset}>
            Cancel
          </Button>
        </div>
      );

    case "settling":
      return (
        <div className="mt-4 text-sm">
          <p className="inline-flex items-center gap-2 text-text">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Settling {formatBaseUnits(state.requirement.amount)} USDC and
            minting your licence...
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            This waits for the ledger and can take a little while. Leaving the
            page does not undo the payment.
          </p>
        </div>
      );

    case "granted": {
      const { outcome } = state;
      const files = Object.keys(outcome.artifact).sort();
      return (
        <div className="mt-4">
          <p className="font-bold text-safe">
            {outcome.licence === "minted"
              ? "Licence minted, skill delivered"
              : "Served with your existing licence, nothing charged"}
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            200 OK, X-STERISH-LICENSE: {outcome.licence}
          </p>
          {outcome.mintTx || outcome.settlement?.transaction ? (
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
              {outcome.settlement?.transaction ? (
                <TxLink hash={outcome.settlement.transaction} label="Payment" />
              ) : null}
              {outcome.mintTx ? (
                <TxLink hash={outcome.mintTx} label="Mint" />
              ) : null}
            </div>
          ) : null}
          <ul className="numeric mt-3 space-y-0.5 font-mono text-xs break-all text-text">
            {files.map((path) => (
              <li key={path}>{path}</li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => download(skillId, version, outcome.artifact)}
            >
              <Download data-icon="inline-start" />
              Download
            </Button>
            {/* The second request is the proof a licence is a purchase, not a
                toll: it comes back 200 with nothing to sign. */}
            <Button variant="ghost" onClick={onStart}>
              <RotateCcw data-icon="inline-start" />
              Request again
            </Button>
          </div>
        </div>
      );
    }

    case "failed": {
      const { title, body } = describeFailure(state.error, state.after);
      const retryable =
        state.error instanceof ApiError &&
        state.error.code === "LICENSE_MINT_PENDING";
      return (
        <div className="mt-4">
          <p className="font-bold text-danger">{title}</p>
          <p className="mt-1 text-sm text-text-secondary">{body}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="outline" onClick={onStart}>
              {retryable ? "Finish minting" : "Start again"}
            </Button>
            <Button variant="ghost" onClick={onReset}>
              Close
            </Button>
          </div>
        </div>
      );
    }
  }
}

export function LicensePanel({
  skillId,
  version,
  verdict,
  isVerified,
}: {
  skillId: string;
  version: string;
  verdict: Verdict;
  isVerified: boolean;
}) {
  const wallet = useWallet();
  const agent = wallet.status === "connected" ? wallet.address : null;
  const licence = useLicense(skillId, version, agent);
  const purchase = usePurchase(skillId, version, agent);

  if (wallet.status === "restoring") {
    return (
      <Strip>
        <Skeleton className="h-8 w-full" aria-hidden />
      </Strip>
    );
  }

  if (!agent) {
    return (
      <Strip>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="inline-flex items-center gap-2 text-sm text-text-secondary">
            <KeyRound className="size-4 shrink-0" aria-hidden />
            {isVerified
              ? `Connect a wallet to see whether you hold a licence for ${version}, or to buy one.`
              : `Connect a wallet to see whether you hold a licence for ${version}.`}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void wallet.connect()}
            disabled={wallet.status === "connecting"}
          >
            <Wallet data-icon="inline-start" />
            Connect wallet
          </Button>
        </div>
      </Strip>
    );
  }

  let status: React.ReactNode;
  if (licence.isPending) {
    status = (
      <p className="inline-flex items-center gap-2 text-sm text-text-secondary">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Reading your licence for {version}...
      </p>
    );
  } else if (licence.error) {
    const error = licence.error;
    status = (
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-warning">
          Could not read your licence for {version}
          {error instanceof ApiError && error.code ? ` (${error.code})` : ""}.
          That is not the same as holding none.
        </p>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void licence.refetch()}
        >
          <RotateCcw data-icon="inline-start" />
          Retry
        </Button>
      </div>
    );
  } else if (licence.data.held && !isVerified) {
    return (
      <Strip tone="danger" alert>
        <p className="flex items-center gap-2 font-bold text-danger">
          <AlertOctagon className="size-5 shrink-0" aria-hidden />
          You hold a licence for {version}, and it is no longer SAFE
        </p>
        <p className="mt-1.5 text-sm text-text-secondary">
          This version is now {verdict}. Your licence is still on chain, but the
          API refuses to serve a version that is not SAFE, and any copy you
          already installed should be removed.
        </p>
      </Strip>
    );
  } else if (licence.data.held) {
    status = (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="inline-flex items-center gap-2 text-sm text-safe">
          <KeyRound className="size-4 shrink-0" aria-hidden />
          You hold a licence for {version}
        </p>
        {purchase.state.step === "idle" ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void purchase.start()}
          >
            <Download data-icon="inline-start" />
            Get the skill
          </Button>
        ) : null}
      </div>
    );
  } else if (isVerified) {
    status = (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="inline-flex items-center gap-2 text-sm text-text-secondary">
          <KeyRound className="size-4 shrink-0" aria-hidden />
          No licence for {version} yet. Bought once per version, never per call.
        </p>
        {purchase.state.step === "idle" ? (
          <Button size="sm" onClick={() => void purchase.start()}>
            Get licence
          </Button>
        ) : null}
      </div>
    );
  } else {
    status = (
      <p className="inline-flex items-center gap-2 text-sm text-text-tertiary">
        <KeyRound className="size-4 shrink-0" aria-hidden />
        Not licensable: only a SAFE version can be bought.
      </p>
    );
  }

  return (
    <Strip
      tone={toneOf(purchase.state)}
      alert={purchase.state.step === "failed"}
    >
      {status}
      <div aria-live="polite">
        <Flow
          skillId={skillId}
          version={version}
          state={purchase.state}
          onStart={() => void purchase.start()}
          onPay={() => void purchase.pay()}
          onReset={purchase.reset}
        />
      </div>
    </Strip>
  );
}
