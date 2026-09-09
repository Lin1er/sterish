"use client";

import { Radio } from "lucide-react";
import { useMemo, useState } from "react";

import { ActivityList } from "@/components/elements/ActivityList";
import { ErrorNotice } from "@/components/elements/ErrorNotice";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { FEED_SCAN_LIMIT, useFeed } from "@/hooks/useFeed";
import { ApiError } from "@/lib/api";
import type { FeedEvent } from "@/lib/types";
import { ActivityFilters, type EventFilter } from "./component/ActivityFilters";

const PAGE_SIZE = 25;

const MATCHES: Record<EventFilter, (event: FeedEvent) => boolean> = {
  all: () => true,
  verdicts: (e) => e.event === "version_recorded" || e.event === "verdict_flipped",
  versions: (e) => e.event === "version_registered",
  skills: (e) => e.event === "skill_registered",
};

function ActivityBody() {
  const [filter, setFilter] = useState<EventFilter>("all");
  const [page, setPage] = useState(0);
  const { data, error, isPending } = useFeed(FEED_SCAN_LIMIT);

  const filtered = useMemo(
    () => (data ? data.events.filter(MATCHES[filter]) : []),
    [data, filter],
  );

  if (isPending) {
    return (
      <div className="space-y-2" aria-busy aria-label="Loading activity">
        {[0, 1, 2, 3, 4, 5, 6, 7].map((row) => (
          <Skeleton key={row} className="h-9 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    // Anything that is not an ApiError is a bug, and the boundary should see it.
    if (!(error instanceof ApiError)) throw error;
    return <ErrorNotice error={error} />;
  }

  if (!data.indexer_enabled) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Radio />
          </EmptyMedia>
          <EmptyTitle>The indexer is not running</EmptyTitle>
          <EmptyDescription>
            Verdicts are still read from the chain, so nothing in the registry
            is affected. Only this timeline and its transaction links depend on
            the index.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  // Filtering and paging happen here rather than in the API, and that is only
  // honest because the whole feed fits in one request: /feed?limit=200 answers
  // in about 0.2s, so these controls see every event, not just a page of them.
  // Past the cap they would start ranking a slice while claiming to rank the
  // set, so the truncation is stated instead of hidden.
  const truncated = data.total > data.events.length;

  const start = page * PAGE_SIZE;
  const visible = filtered.slice(start, start + PAGE_SIZE);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  return (
    <>
      <ActivityFilters
        value={filter}
        onChange={(next) => {
          setFilter(next);
          setPage(0);
        }}
        counts={{
          all: data.events.length,
          verdicts: data.events.filter(MATCHES.verdicts).length,
          versions: data.events.filter(MATCHES.versions).length,
          skills: data.events.filter(MATCHES.skills).length,
        }}
      />

      {truncated ? (
        <p className="mt-4 rounded-lg border border-warning-border bg-warning-surface px-4 py-2.5 text-xs text-warning">
          Showing the most recent {data.events.length} of {data.total} events.
          The filters and counts above cover only those, because the API serves
          at most {FEED_SCAN_LIMIT} events per request and has no filter of its
          own.
        </p>
      ) : null}

      {visible.length === 0 ? (
        <p className="mt-6 rounded-lg border border-border px-4 py-3 text-sm text-text-secondary">
          No events of this kind have been indexed.
        </p>
      ) : (
        <div className="mt-4">
          <ActivityList events={visible} />
        </div>
      )}

      {pages > 1 ? (
        <nav
          aria-label="Activity pages"
          className="mt-6 flex items-center justify-between gap-4"
        >
          <p className="numeric text-sm text-text-secondary">
            {start + 1} to {Math.min(start + PAGE_SIZE, filtered.length)} of{" "}
            {filtered.length}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded-lg border border-border px-3 py-1.5 text-sm transition-colors hover:border-hairline-strong hover:text-keyword disabled:opacity-50 disabled:hover:border-border disabled:hover:text-inherit"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
              disabled={page >= pages - 1}
              className="rounded-lg border border-border px-3 py-1.5 text-sm transition-colors hover:border-hairline-strong hover:text-keyword disabled:opacity-50 disabled:hover:border-border disabled:hover:text-inherit"
            >
              Next
            </button>
          </div>
        </nav>
      ) : null}
    </>
  );
}

/**
 * The audit feed, on its own page.
 *
 * It lives here rather than under the registry table because it answers a
 * different question. The registry asks "what is the state of this skill"; the
 * feed asks "what has been happening". Sharing a page made the second one
 * furniture at the bottom of the first.
 */
export function Activity() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-12">
      <h2 className="mb-6 flex items-center gap-2.5 text-lg font-bold tracking-wider">
        Audit Feed
        {/* A quiet liveness cue instead of a sentence explaining the interval.
            A feed that has silently stopped and a feed with nothing to report
            look identical, and this is the smallest honest way to tell them
            apart. */}
        <span className="inline-flex items-center gap-1.5 rounded-4xl border border-border px-2 py-0.5 text-xs font-normal tracking-normal text-text-secondary">
          <span className="relative flex size-1.5">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-keyword opacity-75" />
            <span className="relative inline-flex size-1.5 rounded-full bg-keyword" />
          </span>
          Live
        </span>
      </h2>
      <ActivityBody />
    </div>
  );
}
