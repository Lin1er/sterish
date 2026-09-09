"use client";

import { Radio } from "lucide-react";
import type { ReactNode } from "react";

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
import { FEED_REFETCH_MS, useFeed } from "@/hooks/useFeed";
import { ApiError } from "@/lib/api";

const FEED_SIZE = 12;

function FeedEmpty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Radio />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{children}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

function FeedBody() {
  const { data, error, isPending } = useFeed(FEED_SIZE);

  if (isPending) {
    return (
      <div className="space-y-2" aria-busy aria-label="Loading the feed">
        {[0, 1, 2, 3, 4].map((row) => (
          <Skeleton key={row} className="h-9 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    // Anything that is not an ApiError is a bug, and the error boundary should
    // see it rather than have it flattened into a tidy notice.
    if (!(error instanceof ApiError)) throw error;
    return <ErrorNotice error={error} />;
  }

  if (!data.indexer_enabled) {
    // A distinct state on purpose. "The indexer is switched off" is not the
    // same fact as "nothing has happened", and only one of them means the
    // registry is quiet.
    return (
      <FeedEmpty title="The indexer is not running">
        Verdicts are still read from the chain, so nothing above is affected.
        Only this activity timeline and the transaction links depend on the
        index.
      </FeedEmpty>
    );
  }

  if (data.events.length === 0) {
    return (
      <FeedEmpty title="No registry activity yet">
        The indexer is running and has seen nothing to report.
      </FeedEmpty>
    );
  }

  return <ActivityList events={data.events} />;
}

/**
 * Recent registry activity, refreshed on a timer.
 *
 * This is the part of the dashboard that shows Sterish is a live system rather
 * than a rendered snapshot: run the pipeline against a new skill and the
 * verdict appears here without anybody reloading. The interval is stated in
 * the heading rather than left for the reader to guess, because a feed that
 * silently stopped updating and a feed with nothing to report look identical.
 */
export function LiveFeed() {
  return (
    <section className="mt-16">
      <h2 className="mb-1 flex items-center gap-2 text-lg font-bold tracking-wider">
        <Radio className="size-4 text-keyword" aria-hidden />
        Live Audit Feed
      </h2>
      <p className="mb-4 text-sm text-text-secondary">
        Registry events as the indexer sees them, newest first, refreshed every{" "}
        {FEED_REFETCH_MS / 1000} seconds. Each line links to the transaction
        that produced it.
      </p>
      <FeedBody />
    </section>
  );
}
