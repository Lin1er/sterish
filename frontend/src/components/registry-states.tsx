import { PlugZap, ServerCrash } from "lucide-react";

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import type { ApiError } from "@/lib/api/client";

/**
 * The shape of the table, held while the registry read is in flight.
 *
 * Sized to the real rows rather than a spinner, so the page does not jump when
 * the data lands.
 */
export function RegistrySkeleton() {
  return (
    <div className="space-y-2" aria-busy aria-label="Loading the registry">
      <Skeleton className="h-9 w-full" />
      {[0, 1, 2, 3, 4].map((row) => (
        <Skeleton key={row} className="h-12 w-full" />
      ))}
    </div>
  );
}

/**
 * A failed read, told apart from an empty registry.
 *
 * These are two completely different facts and the old scaffold blurred them:
 * "no skills are registered" and "we could not ask" must never look alike,
 * because only one of them means the registry is trustworthy and quiet. The
 * copy also names the URL that failed, since the usual cause is
 * NEXT_PUBLIC_API_URL pointing somewhere that is not running.
 */
export function RegistryError({ error }: { error: ApiError }) {
  const transport = error.isTransport;
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          {transport ? <PlugZap /> : <ServerCrash />}
        </EmptyMedia>
        <EmptyTitle>
          {transport
            ? "Cannot reach the verification API"
            : "The verification API returned an error"}
        </EmptyTitle>
        <EmptyDescription>
          {error.message}
          {error.code ? ` (${error.code})` : null}
        </EmptyDescription>
      </EmptyHeader>
      <p className="numeric mt-2 font-mono text-xs text-text-tertiary">
        {error.url}
      </p>
      <p className="mt-4 max-w-md text-sm text-text-secondary">
        Nothing is shown above rather than a cached or default verdict. An
        unreachable registry is not evidence that a skill is safe.
      </p>
    </Empty>
  );
}
