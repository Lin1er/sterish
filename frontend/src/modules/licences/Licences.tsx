"use client";

import {
  AlertOctagon,
  Download,
  ExternalLink,
  KeyRound,
  Loader2,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { CopyHash } from "@/components/elements/CopyHash";
import { VerdictBadge } from "@/components/elements/VerdictBadge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useLicences, useLicenceVerdicts } from "@/hooks/useLicences";
import { useWallet } from "@/hooks/useWallet";
import { ApiError, requestSkill } from "@/lib/api";
import { downloadArtifact } from "@/lib/artifact";
import {
  TOKENS_CONTRACT_ID,
  isAccountAddress,
  type Licence,
} from "@/lib/tokens";
import type { VersionCheck } from "@/lib/types";
import { EXPLORER_BASE } from "@/lib/wallet";
import { formatLedgerTime } from "@/utils/format";

/**
 * Every licence one address holds, with the verdict of each version today.
 *
 * Any address, not only the connected one: a licence is a soulbound token on a
 * public ledger, readable by anybody on stellar.expert. This page shows it; it
 * reveals nothing that was private.
 *
 * Licences for versions that are no longer SAFE are listed first and flagged.
 * Holding a licence for a version that was re-audited DANGEROUS is the state a
 * holder most needs to hear about, and a chronological list would bury it.
 */

function AddressForm({ initial }: { initial: string }) {
  const router = useRouter();
  const [value, setValue] = useState(initial);
  const trimmed = value.trim();
  const invalid = trimmed !== "" && !isAccountAddress(trimmed);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!isAccountAddress(trimmed)) return;
    router.push(`/licences/${trimmed}`);
  }

  return (
    <form onSubmit={submit} className="mt-6">
      <label htmlFor="licences-address" className="text-xs text-text-tertiary">
        Stellar account
      </label>
      <div className="mt-2 flex flex-col gap-3 sm:flex-row">
        <Input
          id="licences-address"
          className="h-11 px-4 font-mono text-sm md:text-sm"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="G..."
          spellCheck={false}
          autoComplete="off"
          aria-invalid={invalid}
        />
        <Button
          type="submit"
          size="lg"
          className="h-11 px-4"
          disabled={!isAccountAddress(trimmed)}
        >
          <Search data-icon="inline-start" />
          Show licences
        </Button>
      </div>
      {invalid ? (
        <p className="mt-2 text-xs text-danger">
          {/^[CM]/.test(trimmed)
            ? "Only a classic G... account can hold a licence. Contract and muxed addresses cannot."
            : "A Stellar account is 56 characters starting with G."}
        </p>
      ) : null}
    </form>
  );
}

function LicenceRow({
  licence,
  verdict,
  own,
}: {
  licence: Licence;
  verdict: { data?: VersionCheck; error: Error | null; isPending: boolean };
  own: boolean;
}) {
  const wallet = useWallet();
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const safe = verdict.data?.is_verified === true;

  async function getSkill() {
    if (!wallet.address) return;
    setState("loading");
    setMessage(null);
    try {
      const outcome = await requestSkill(licence.skillId, licence.version, {
        agent: wallet.address,
      });
      if (outcome.kind === "granted") {
        downloadArtifact(licence.skillId, licence.version, outcome.artifact);
        setState("idle");
      } else {
        setState("error");
        setMessage(
          "The API asked for payment, so the licence was not recognised.",
        );
      }
    } catch (cause) {
      setState("error");
      setMessage(
        cause instanceof ApiError
          ? `${cause.message}${cause.code ? ` (${cause.code})` : ""}`
          : String(cause),
      );
    }
  }

  return (
    <li className="flex flex-col gap-2 py-4 sm:flex-row sm:items-center sm:gap-4">
      <div className="min-w-0 flex-1">
        <Link
          href={`/skills/${encodeURIComponent(licence.skillId)}#version-${encodeURIComponent(licence.version)}`}
          className="numeric font-mono text-sm break-all hover:text-keyword hover:underline"
        >
          {licence.skillId}
          {/* The version never splits: "2026.8.3" on one line and "1" on the
              next reads as a different version. The id may wrap, it is long. */}
          <span className="whitespace-nowrap text-text-tertiary">
            @{licence.version}
          </span>
        </Link>
        <p className="numeric mt-1 text-xs text-text-tertiary">
          Minted {formatLedgerTime(licence.mintedAt)} UTC, token #
          {licence.tokenId}
        </p>
        {message ? <p className="mt-1 text-xs text-danger">{message}</p> : null}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {verdict.isPending ? (
          <Skeleton className="h-5 w-20" aria-label="Reading verdict" />
        ) : verdict.data ? (
          <VerdictBadge verdict={verdict.data.verdict} />
        ) : (
          <span className="text-xs text-warning">verdict unavailable</span>
        )}
        {own && safe ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void getSkill()}
            disabled={state === "loading"}
          >
            {state === "loading" ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Download data-icon="inline-start" />
            )}
            Get the skill
          </Button>
        ) : null}
      </div>
    </li>
  );
}

function LicenceList({ address }: { address: string }) {
  const wallet = useWallet();
  const scan = useLicences(address);
  const licences = scan.data?.licences ?? [];
  const verdicts = useLicenceVerdicts(licences);
  const own = wallet.status === "connected" && wallet.address === address;

  if (scan.isPending) {
    return (
      <div className="mt-8 space-y-3" aria-busy aria-label="Reading licences">
        <p className="text-xs text-text-secondary">
          Reading every token from the tokens contract...
        </p>
        {[0, 1, 2].map((row) => (
          <Skeleton key={row} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  if (scan.error) {
    return (
      <Empty className="mt-8">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <AlertOctagon />
          </EmptyMedia>
          <EmptyTitle>Could not read the tokens contract</EmptyTitle>
          <EmptyDescription>
            {scan.error.message}. This is not the same as holding no licences:
            nothing is listed because nothing could be read.
          </EmptyDescription>
        </EmptyHeader>
        <Button variant="outline" onClick={() => void scan.refetch()}>
          Try again
        </Button>
      </Empty>
    );
  }

  const rows = licences.map((licence, i) => ({
    licence,
    verdict: verdicts[i],
  }));
  // Not SAFE first, then newest. A pending or failed verdict read stays in
  // chronological place rather than being treated as unsafe.
  const flagged = rows.filter(
    (r) => r.verdict?.data && !r.verdict.data.is_verified,
  );
  const rest = rows.filter((r) => !flagged.includes(r));

  const source = (
    <p className="mt-8 text-xs text-text-tertiary">
      Read directly from the{" "}
      <a
        href={`${EXPLORER_BASE}/contract/${TOKENS_CONTRACT_ID}`}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-keyword hover:underline"
      >
        tokens contract
        <ExternalLink className="size-3" aria-hidden />
      </a>
      , {scan.data.scanned} tokens scanned. Verdicts are read per version from
      the registry. This page reads the chain token by token until the API
      serves this list itself.
    </p>
  );

  if (licences.length === 0) {
    return (
      <>
        <Empty className="mt-8">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <KeyRound />
            </EmptyMedia>
            <EmptyTitle>No licences</EmptyTitle>
            <EmptyDescription>
              {own
                ? "This wallet has not bought a licence yet. A licence is bought once per version, from the version card on a skill's page."
                : "This account holds no licence for any skill version."}
            </EmptyDescription>
          </EmptyHeader>
          {own ? (
            <Button
              variant="outline"
              render={<Link href="/" />}
              nativeButton={false}
            >
              Browse the registry
            </Button>
          ) : null}
        </Empty>
        {source}
      </>
    );
  }

  return (
    <>
      {flagged.length > 0 ? (
        <div
          role="alert"
          className="mt-8 rounded-lg border border-danger-border bg-danger-surface px-5 py-4"
        >
          <p className="flex items-center gap-2 font-bold text-danger">
            <AlertOctagon className="size-5 shrink-0" aria-hidden />
            {flagged.length === 1
              ? "One licensed version is no longer SAFE"
              : `${flagged.length} licensed versions are no longer SAFE`}
          </p>
          <p className="mt-1.5 max-w-2xl text-sm text-text-secondary">
            The licences are still on chain, but the API refuses to serve a
            version that is not SAFE, and any copy already installed should be
            removed. They are listed first below.
          </p>
        </div>
      ) : null}

      <h3 className="mt-8 text-sm text-text-secondary">
        {licences.length} licence{licences.length === 1 ? "" : "s"}
      </h3>
      <ol className="mt-2 divide-y divide-border border-y border-border">
        {[...flagged, ...rest].map(({ licence, verdict }) => (
          <LicenceRow
            key={licence.tokenId}
            licence={licence}
            verdict={verdict}
            own={own}
          />
        ))}
      </ol>
      {source}
    </>
  );
}

export function Licences({ address }: { address: string | null }) {
  const wallet = useWallet();
  const router = useRouter();

  // /licences with a connected wallet means "mine".
  useEffect(() => {
    if (address === null && wallet.status === "connected" && wallet.address) {
      router.replace(`/licences/${wallet.address}`);
    }
  }, [address, router, wallet.address, wallet.status]);

  const own =
    address !== null &&
    wallet.status === "connected" &&
    wallet.address === address;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
      <h2 className="text-lg font-bold tracking-wider">
        {own ? "Your licences" : "Licences"}
      </h2>
      <p className="mt-2 max-w-2xl text-sm text-text-secondary">
        A licence is a soulbound token, bought once for one exact version and
        public on the ledger, so any account&apos;s licences can be looked up.
      </p>

      {address !== null && isAccountAddress(address) ? (
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <CopyHash value={address} chars={8} />
          <a
            href={`${EXPLORER_BASE}/account/${address}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-keyword hover:underline"
          >
            Account on stellar.expert
            <ExternalLink className="size-3" aria-hidden />
          </a>
        </div>
      ) : null}

      <AddressForm key={address ?? ""} initial={address ?? ""} />

      {address === null ? null : isAccountAddress(address) ? (
        <LicenceList address={address} />
      ) : (
        <Empty className="mt-8">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <AlertOctagon />
            </EmptyMedia>
            <EmptyTitle>Not a Stellar account</EmptyTitle>
            <EmptyDescription>
              <span className="font-mono break-all">{address}</span> is not a
              classic G... account, so it cannot hold a licence.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
    </div>
  );
}
