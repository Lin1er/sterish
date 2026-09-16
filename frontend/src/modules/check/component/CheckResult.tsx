import {
  ArrowRight,
  ChevronDown,
  FileWarning,
  ShieldQuestion,
} from "lucide-react";
import Link from "next/link";

import { CopyHash } from "@/components/elements/CopyHash";
import { ErrorNotice } from "@/components/elements/ErrorNotice";
import { EvidenceLinks } from "@/components/elements/EvidenceLinks";
import { VerdictBanner } from "@/components/elements/VerdictBanner";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import type { ApiError } from "@/lib/api";
import type { ContentHashError } from "@/lib/contentHash";
import type { VersionCheck } from "@/lib/types";
import { formatLedgerTime, shortAddress } from "@/utils/format";

/** What was asked, kept beside the answer so the answer can be read against it. */
export type CheckQuery =
  | { by: "files"; hash: string; files: string[]; excluded: string[] }
  | { by: "hash"; hash: string }
  | { by: "name"; skillId: string; version: string };

export type CheckState =
  | { status: "idle" }
  | { status: "working"; label: string }
  | { status: "answered"; query: CheckQuery; result: VersionCheck }
  | { status: "unknown"; query: CheckQuery; error: ApiError }
  | { status: "unhashable"; error: ContentHashError }
  | { status: "failed"; error: ApiError };

function FileList({ query }: { query: Extract<CheckQuery, { by: "files" }> }) {
  return (
    <Collapsible className="rounded-lg border border-border text-sm">
      <CollapsibleTrigger className="group flex w-full items-center justify-between gap-3 rounded-lg px-4 py-3 text-left text-text-secondary transition-colors hover:text-text focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
        <span>
          Hashed {query.files.length} file{query.files.length === 1 ? "" : "s"}
          {query.excluded.length > 0
            ? `, left out ${query.excluded.length} the packager excludes`
            : null}
        </span>
        <ChevronDown
          className="size-4 shrink-0 transition-transform group-data-panel-open:rotate-180"
          aria-hidden
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="border-t border-border px-4 py-3">
        <ul className="numeric space-y-1 font-mono text-xs break-all text-text">
          {query.files.map((path) => (
            <li key={path}>{path}</li>
          ))}
        </ul>
        {query.excluded.length > 0 ? (
          <ul className="numeric mt-3 space-y-1 font-mono text-xs break-all text-text-tertiary">
            {query.excluded.map((path) => (
              <li key={path}>
                <s>{path}</s>
              </li>
            ))}
          </ul>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

function Answered({
  query,
  result,
}: {
  query: CheckQuery;
  result: VersionCheck;
}) {
  // The API echoes the hash back so a client can assert it got an answer about
  // what it asked. If that ever fails, nothing below may be shown as a verdict
  // for these bytes.
  if (query.by !== "name" && result.content_hash !== query.hash) {
    return (
      <p
        role="alert"
        className="rounded-lg border border-danger-border bg-danger-surface px-4 py-3 text-sm text-danger"
      >
        The API answered about a different content hash than the one asked for (
        {result.content_hash}). Treat these bytes as unverified.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-secondary">
        {query.by === "name" ? "The registry holds" : "These bytes are"}{" "}
        <Link
          href={`/skills/${encodeURIComponent(result.skill_id)}`}
          className="numeric font-mono text-text hover:text-keyword hover:underline"
        >
          {result.skill_id}@{result.version}
        </Link>
      </p>

      <VerdictBanner
        verdict={result.verdict}
        version={result.version}
        trustScore={result.audited_at === null ? null : result.trust_score}
      />

      {query.by === "name" ? (
        // Spec 3.2: asking by name trusts the name. Worth saying at the moment
        // somebody might act on it.
        <p className="rounded-lg border border-border px-4 py-3 text-sm text-text-secondary">
          This answer is about the name, not about any files you have. Before
          installing, check the files themselves: a copy with one byte changed
          carries the same name and none of this verdict.
        </p>
      ) : null}

      <dl className="flex flex-wrap gap-x-10 gap-y-3">
        <div>
          <dt className="text-xs text-text-tertiary">Content hash</dt>
          <dd className="mt-1">
            <CopyHash value={result.content_hash} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-text-tertiary">Auditor</dt>
          <dd
            className="numeric mt-1 font-mono text-xs"
            title={result.auditor ?? undefined}
          >
            {result.auditor ? shortAddress(result.auditor) : "none"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-text-tertiary">Audited at</dt>
          <dd className="numeric mt-1 font-mono text-xs">
            {result.audited_at === null
              ? "never"
              : formatLedgerTime(result.audited_at)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-text-tertiary">Verified badge</dt>
          <dd className="numeric mt-1 font-mono text-xs">
            {result.is_verified ? "yes" : "no"}
          </dd>
        </div>
      </dl>

      {query.by === "files" ? <FileList query={query} /> : null}

      <EvidenceLinks evidence={result.evidence} />

      {/* Only SAFE is licensable, so only SAFE gets a way forward. Every other
          verdict's banner already says what to do instead. */}
      {result.is_verified ? (
        <Link
          href={`/skills/${encodeURIComponent(result.skill_id)}#version-${encodeURIComponent(result.version)}`}
          className="inline-flex items-center gap-1.5 text-sm text-keyword hover:underline"
        >
          Get a licence for {result.version}
          <ArrowRight className="size-4" aria-hidden />
        </Link>
      ) : null}
    </div>
  );
}

function Unknown({ query, error }: { query: CheckQuery; error: ApiError }) {
  if (query.by === "name") {
    const what =
      error.code === "VERSION_NOT_FOUND"
        ? `${query.skillId} is registered, but has no version ${query.version}.`
        : `No skill named ${query.skillId} is registered.`;
    return (
      <div className="rounded-lg border border-unaudited-border bg-unaudited-surface px-5 py-4 text-unaudited">
        <p className="flex items-center gap-2 font-bold">
          <ShieldQuestion className="size-5 shrink-0" aria-hidden />
          Not in the registry
        </p>
        <p className="mt-1.5 max-w-2xl text-sm text-text-secondary">
          {what} Nothing has been audited under that name, so there is no
          verdict to rely on.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div
        role="alert"
        className="rounded-lg border border-unaudited-border bg-unaudited-surface px-5 py-4 text-unaudited"
      >
        <p className="flex items-center gap-2 font-bold">
          <ShieldQuestion className="size-5 shrink-0" aria-hidden />
          Unaudited: these bytes are unknown
        </p>
        <p className="mt-1.5 max-w-2xl text-sm text-text-secondary">
          No version in the registry has this content hash, so no auditor has
          ever looked at these exact bytes. That is not a pass. If you expected
          a known skill, a single changed byte is enough to end up here: do not
          install it on the strength of the name.
        </p>
        <div className="mt-3">
          <CopyHash value={query.hash} />
        </div>
      </div>
      {query.by === "files" ? <FileList query={query} /> : null}
    </div>
  );
}

export function CheckResult({ state }: { state: CheckState }) {
  switch (state.status) {
    case "idle":
      return null;
    case "working":
      return (
        <div aria-busy className="space-y-3">
          <p className="text-sm text-text-secondary">{state.label}</p>
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      );
    case "answered":
      return <Answered query={state.query} result={state.result} />;
    case "unknown":
      return <Unknown query={state.query} error={state.error} />;
    case "unhashable":
      return (
        <div
          role="alert"
          className="rounded-lg border border-warning-border bg-warning-surface px-5 py-4 text-warning"
        >
          <p className="flex items-center gap-2 font-bold">
            <FileWarning className="size-5 shrink-0" aria-hidden />
            These files cannot be hashed
          </p>
          <p className="mt-1.5 max-w-2xl text-sm text-text-secondary">
            {state.error.kind === "NotUtf8"
              ? "One of the files is not UTF-8 text. Content hash v1 covers text skills only, so no skill with a binary file can be registered or checked."
              : state.error.kind === "EmptyFileSet"
                ? "Nothing was left to hash once the excluded files were removed."
                : state.error.message}
          </p>
        </div>
      );
    case "failed":
      return <ErrorNotice error={state.error} />;
  }
}
