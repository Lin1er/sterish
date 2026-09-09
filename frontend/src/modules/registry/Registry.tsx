import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { Suspense } from "react";

import { listSkills } from "@/lib/api";
import { getQueryClient, queryKeys } from "@/lib/queryClient";
import { RegistryContent } from "./component/RegistryContent";
import { RegistrySkeleton } from "./component/RegistrySkeleton";

/**
 * 20, not the 50 the spec allows. GET /skills costs about 0.44s per row
 * against the live API, so 50 rows is a 22 second wait. Paging is the
 * compromise until that fan-out is batched.
 */
const PAGE_SIZE = 20;

/**
 * A hand-edited query string is user input. Anything that is not a
 * non-negative integer falls back to the first page rather than being passed
 * through to the API to be rejected there.
 */
function parseStart(raw: string | string[] | undefined): number {
  const value = Number(Array.isArray(raw) ? raw[0] : raw);
  return Number.isInteger(value) && value >= 0 ? value : 0;
}

/**
 * The registry.
 *
 * The read happens here, on the server, so the rows are in the first HTML the
 * browser receives and the API never has to be reachable from the visitor's
 * network. The result is then dehydrated into React Query, so the client picks
 * up the same data instead of fetching it a second time, and every later page
 * is cached.
 *
 * prefetchQuery does not throw: a failed read arrives on the client as the
 * query's error, which is where ErrorNotice renders it.
 */
async function PrefetchedRegistry({ offset }: { offset: number }) {
  const queryClient = getQueryClient();

  await queryClient.prefetchQuery({
    queryKey: queryKeys.skills(offset, PAGE_SIZE),
    queryFn: () => listSkills({ start: offset, limit: PAGE_SIZE }),
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RegistryContent initialStart={offset} pageSize={PAGE_SIZE} />
    </HydrationBoundary>
  );
}

export function Registry({
  start,
}: {
  start: string | string[] | undefined;
}) {
  const offset = parseStart(start);

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
      {/* No hero. The pitch belongs on the landing page (STE-23); this route is
          the tool, and a tool should open on its data. */}
      <section>
        <h2 className="mb-6 text-lg font-bold tracking-wider">
          Registry Browser
        </h2>
        {/* The await lives below this boundary, not in Registry itself, so the
            page shell paints immediately and only the table waits on the ten
            second read. */}
        <Suspense fallback={<RegistrySkeleton />}>
          <PrefetchedRegistry offset={offset} />
        </Suspense>
      </section>
    </div>
  );
}
