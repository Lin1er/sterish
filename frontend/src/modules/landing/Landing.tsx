import { Suspense } from "react";

import { API_BASE_URL } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { RugPull } from "./component/RugPull";
import { RUG_PULL_SKILL, getLandingStats, getRugPull } from "./liveStats";

/**
 * The landing page (STE-23): one scroll from "what is this" to "check it
 * yourself".
 *
 * Every number on this page is read from the live registry at render time
 * (liveStats.ts). Every technical claim was verified before it was written:
 * the two CVEs against their published advisories, the x402 and USDC SAC
 * wording against Stellar's own docs through MCP Stellar Raven, and the rug
 * pull against the contract. Notes and sources are in
 * docs/evidence/ste-23-landing-claims-2026-09-20.json.
 *
 * Colours, type and spacing come only from the STE-7 tokens in globals.css.
 *
 * The two registry reads sit behind their own Suspense boundaries rather than
 * being awaited before anything renders. GET /skills costs about 2.8s against
 * the live API, so awaiting it up front meant a 3.5s blank page — measured, in
 * a production build. This is the page we send to people who have never heard
 * of us, and a blank page is the worst possible first frame. The prose paints
 * at once and the numbers arrive when the chain answers.
 *
 * Caching them instead was the obvious alternative and was rejected: the
 * shared API client sets cache: "no-store" on purpose (api-spec §4 — a stale
 * verdict is the worst thing this product can serve), and Next 16's `use
 * cache` needs cacheComponents enabled app-wide, which would change that
 * guarantee for the dashboard too. Streaming buys the same result without
 * touching anyone else's correctness.
 */

const X_URL = "https://x.com/sterishxyz";
/** Public since 24 September 2026 (docs/deployments.md). */
const DASHBOARD_URL = "https://app.sterish.xyz";
const REGISTRY_CONTRACT = "CCZJN366SV57JEBZVXGYY3ZBLJNFV4IR5ILCAI3EMX2WDNQPEPQ4BRL2";
const EXPERT = `https://stellar.expert/explorer/testnet/contract/${REGISTRY_CONTRACT}`;

export function Landing() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8">
      <Hero />
      <Problem />
      <HowItWorks />
      <WhyStellar />
      <Evidence />
      <Close />
    </div>
  );
}

/** Awaits the two versions of the rug pull; the rest of the hero does not. */
async function RugPullLoader() {
  return <RugPull data={await getRugPull()} />;
}

async function ProofLoader() {
  return <Proof stats={await getLandingStats()} />;
}

function Hero() {
  return (
    <section className="grid items-center gap-10 py-14 sm:py-20 lg:grid-cols-2 lg:gap-14">
      <div>
        <h1 className="text-4xl leading-[1.08] font-semibold tracking-tight sm:text-5xl lg:text-6xl">
          Your agent trusts the name.
          <br />
          <span className="text-keyword">Attackers change the bytes.</span>
        </h1>
        <p className="mt-6 max-w-xl text-lg text-text-secondary">
          Sterish audits AI agent skills and writes the verdict on chain,
          pinned to the hash of the exact files it read. Anyone can check a
          specific version before installing it, without taking the
          publisher&rsquo;s word for anything.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <a
            href={`${API_BASE_URL}/skills`}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg bg-primary px-5 py-3 font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            Open the live registry
          </a>
          <a
            href={DASHBOARD_URL}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-hairline-strong px-5 py-3 transition-colors hover:border-keyword hover:text-keyword"
          >
            Open the dashboard
          </a>
        </div>
        <p className="mt-4 font-mono text-xs text-text-tertiary">
          Stellar testnet. Real transactions, no mainnet funds.
        </p>
      </div>

      <Suspense fallback={<CardSkeleton />}>
        <RugPullLoader />
      </Suspense>
    </section>
  );
}

function Problem() {
  return (
    <Section
      eyebrow="The problem"
      title="Tool poisoning is an attack class, not a hypothetical"
    >
      <div className="grid gap-6 lg:grid-cols-2">
        <p className="text-lg text-text-secondary">
          An agent skill is instructions the model will follow, handed over
          with the agent&rsquo;s own authority. Nothing in the format carries
          provenance, and nothing checks that what you approved is what later
          runs. Two published advisories show both halves of that going wrong.
        </p>
        <div className="space-y-4">
          <Cve
            id="CVE-2025-54136"
            score="CVSS 8.8"
            name="“MCPoison” · Cursor IDE"
            body="Approval was remembered under an MCP entry's name. An attacker could commit a harmless config, wait for a developer to approve it, then swap the command it ran — with no new prompt. Patched in Cursor 1.3."
          />
          <Cve
            id="CVE-2025-6514"
            score="CVSS 9.6"
            name="mcp-remote · 437,000+ downloads"
            body="OS command injection in versions 0.0.5 to 0.1.15: the first documented case of full remote code execution on a client machine caused by connecting to an untrusted MCP server."
          />
        </div>
      </div>

      <p className="mt-8 border-l-2 border-keyword pl-5 text-lg">
        The first one is the whole argument. Approval was bound to a{" "}
        <strong>name</strong>. Sterish binds the verdict to a{" "}
        <strong>content hash</strong>, so a changed byte is a different skill
        and carries no badge.
      </p>

      <p className="mt-6 text-text-secondary">
        Meanwhile the skills an agent installs today arrive with no security
        signal at all — no audit, no provenance, nothing between reading a
        README and running it.
      </p>
    </Section>
  );
}

function Cve({
  id,
  score,
  name,
  body,
}: {
  id: string;
  score: string;
  name: string;
  body: string;
}) {
  return (
    <div className="rounded-lg border border-danger-border bg-danger-surface p-5">
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-sm font-medium text-danger">{id}</span>
        <span className="font-mono text-xs text-text-tertiary">{score}</span>
      </p>
      <p className="mt-1 text-sm text-text">{name}</p>
      <p className="mt-3 text-sm text-text-secondary">{body}</p>
    </div>
  );
}

/** A real sequence, so it is numbered. Order carries information here. */
const STEPS = [
  {
    n: "01",
    title: "Register",
    body: "A publisher registers a skill version against the sha256 of its files. The Registry contract refuses a hash it has already seen.",
  },
  {
    n: "02",
    title: "Audit, three stages",
    body: "Structural checks, then declared-versus-actual static analysis, then an LLM pass over the prose an agent would obey. Each stage can only make the verdict worse.",
  },
  {
    n: "03",
    title: "Verdict on chain",
    body: "Safe, Warning, Dangerous or Unaudited, plus a trust score, written to the Registry against that hash. Only Safe mints a VERIFIED badge.",
  },
  {
    n: "04",
    title: "Pay per use",
    body: "An agent calling a paid skill gets HTTP 402, pays in USDC over x402, and a soulbound licence token is minted to its address.",
  },
  {
    n: "05",
    title: "Use",
    body: "The next request carries proof of that licence and returns 200. No account, no subscription, no human in the loop.",
  },
];

function HowItWorks() {
  return (
    <Section eyebrow="How it works" title="Register, audit, verdict, pay, use">
      <ol className="grid gap-px overflow-hidden rounded-lg border border-hairline bg-hairline sm:grid-cols-2 lg:grid-cols-5">
        {STEPS.map((s) => (
          <li key={s.n} className="bg-surface p-5">
            <p className="font-mono text-xs tracking-widest text-keyword">
              {s.n}
            </p>
            <p className="mt-3 font-medium">{s.title}</p>
            <p className="mt-2 text-sm text-text-secondary">{s.body}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}

function WhyStellar() {
  return (
    <Section eyebrow="Why Stellar" title="Three properties, one sentence">
      <p className="max-w-4xl text-xl leading-relaxed sm:text-2xl">
        A verdict written on chain and pinned to the content hash{" "}
        <span className="text-text-secondary">cannot be forged</span>, a
        slashable USDC bond{" "}
        <span className="text-text-secondary">keeps auditors honest</span>, and
        x402{" "}
        <span className="text-text-secondary">
          lets an agent pay per use with no account
        </span>
        .
      </p>

      <div className="mt-10 grid gap-5 lg:grid-cols-3">
        <Point title="Pinned to bytes">
          The badge belongs to a hash, not to a name or a publisher. Change one
          byte and the hash changes completely, so the new version starts again
          at Unaudited.
        </Point>
        <Point title="Auditors have money at risk">
          An auditor locks a USDC bond in escrow before the audit. A verdict
          shown to be wrong is slashed to whoever reported it, settled by the
          contract rather than by us.
        </Point>
        <Point title="Machine-native payment">
          x402 turns HTTP 402 into a usable payment step. The agent pays in
          USDC, receives a soulbound licence, and continues — no signup, no
          card, no human.
        </Point>
      </div>
    </Section>
  );
}

function Point({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-hairline bg-surface p-5">
      <p className="font-medium">{title}</p>
      <p className="mt-2 text-sm text-text-secondary">{children}</p>
    </div>
  );
}

/** The section frame paints at once; only the figures inside it wait. */
function Evidence() {
  return (
    <Section eyebrow="Evidence" title="What is on chain right now">
      <Suspense fallback={<StatsSkeleton />}>
        <ProofLoader />
      </Suspense>
    </Section>
  );
}

function Proof({ stats }: { stats: Awaited<ReturnType<typeof getLandingStats>> }) {
  return (
    <>
      <div className="grid gap-px overflow-hidden rounded-lg border border-hairline bg-hairline sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          value={`${stats.catalogueSafe}/${stats.catalogue}`}
          label="Official skills.stellar.org catalogue skills audited, zero exclusions"
        />
        <Stat
          value={`${stats.poisonedCaught}/${stats.poisoned}`}
          label="Poisoned fixtures correctly caught as Dangerous"
          tone="danger"
        />
        <Stat
          value={String(stats.verified)}
          label="Versions holding a VERIFIED badge on chain"
          tone="safe"
        />
        <Stat
          value={String(stats.shown)}
          label={`Skills listed publicly, of ${stats.onChain} on chain`}
        />
      </div>

      <p className="mt-4 text-sm text-text-secondary">
        {stats.onChain - stats.shown === stats.hiddenTest ? (
          <>
            The registry holds {stats.onChain} entries; {stats.hiddenTest} are
            test namespaces from our own integration runs and are filtered out
            of the public list. They are not hidden: the API reports the count
            on every response, and <code className="font-mono">?include_test=true</code>{" "}
            returns everything.
          </>
        ) : (
          <>
            The registry holds {stats.onChain} entries, of which {stats.shown}{" "}
            are listed publicly. The API reports what it filters on every
            response.
          </>
        )}{" "}
        {stats.live ? (
          <>Read live at page load, {stats.asOf}.</>
        ) : (
          <span className="text-warning">
            The registry did not answer; these are verified figures from{" "}
            {stats.asOf}.
          </span>
        )}
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <EvidenceLink
          href={`${API_BASE_URL}/check/${RUG_PULL_SKILL}/2.0.0`}
          title="The rug pull, as the API answers it"
          body="Version 2 of a skill whose version 1 is Safe. Dangerous, trust 10, no badge."
        />
        <EvidenceLink
          href={EXPERT}
          title="The Registry contract on stellar.expert"
          body="Every verdict above was written by a transaction you can open and read."
        />
      </div>

      <p className="mt-6 font-mono text-xs text-text-tertiary">
        Stellar testnet resets to genesis on 16 December 2026; links to
        stellar.expert have that expiry date.
      </p>
    </>
  );
}

function Stat({
  value,
  label,
  tone,
}: {
  value: string;
  label: string;
  tone?: "safe" | "danger";
}) {
  return (
    <div className="bg-surface p-5">
      <p
        className="font-mono text-3xl font-semibold"
        style={
          tone ? { color: `var(--${tone === "safe" ? "safe" : "danger"})` } : undefined
        }
      >
        {value}
      </p>
      <p className="mt-2 text-sm text-text-secondary">{label}</p>
    </div>
  );
}

function EvidenceLink({
  href,
  title,
  body,
}: {
  href: string;
  title: string;
  body: string;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="block rounded-lg border border-hairline bg-surface p-5 transition-colors hover:border-hairline-strong"
    >
      <p className="font-medium text-keyword underline underline-offset-4">
        {title}
      </p>
      <p className="mt-2 text-sm text-text-secondary">{body}</p>
    </a>
  );
}

function Close() {
  return (
    <section className="border-t border-hairline py-14 sm:py-20">
      <h2 className="max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">
        Check a skill before your agent runs it.
      </h2>
      <p className="mt-4 max-w-2xl text-text-secondary">
        The verification API is public and needs no key. Ask by hash if you
        want a security answer — asking by name trusts the name.
      </p>
      <div className="mt-8 flex flex-wrap items-center gap-3">
        <a
          href={DASHBOARD_URL}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg bg-primary px-5 py-3 font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          Browse the registry
        </a>
        <a
          href={X_URL}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg border border-hairline-strong px-5 py-3 transition-colors hover:border-keyword hover:text-keyword"
        >
          Follow @sterishxyz
        </a>
      </div>
      <p className="mt-10 font-mono text-xs text-text-tertiary">
        Instawards by @StellarOrg. Sterish is an audit registry for agent
        skills — not an official Stellar product, and not an app store.
      </p>
    </section>
  );
}

/** Holds the card's height so the hero does not jump when the read lands. */
function CardSkeleton() {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-5">
      <Skeleton className="h-3 w-12" />
      <Skeleton className="mt-2 h-5 w-full max-w-sm" />
      <Skeleton className="mt-6 h-6 w-28" />
      <Skeleton className="mt-4 h-3 w-24" />
      <Skeleton className="mt-2 h-4 w-full" />
      <Skeleton className="mt-1 h-4 w-2/3" />
      <Skeleton className="mt-5 h-4 w-full max-w-xs" />
    </div>
  );
}

function StatsSkeleton() {
  return (
    <div className="grid gap-px overflow-hidden rounded-lg border border-hairline bg-hairline sm:grid-cols-2 lg:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="bg-surface p-5">
          <Skeleton className="h-8 w-20" />
          <Skeleton className="mt-3 h-3 w-full" />
          <Skeleton className="mt-1 h-3 w-2/3" />
        </div>
      ))}
    </div>
  );
}

function Section({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-hairline py-14 sm:py-20">
      <p className="font-mono text-xs uppercase tracking-widest text-tan">
        {eyebrow}
      </p>
      <h2 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">
        {title}
      </h2>
      <div className="mt-8">{children}</div>
    </section>
  );
}
