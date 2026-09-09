import { Suspense } from "react";

import { ErrorNotice } from "@/components/elements/ErrorNotice";
import { ApiError, listSkills } from "@/lib/api";
import { RegistryPagination } from "./component/RegistryPagination";
import { RegistrySkeleton } from "./component/RegistrySkeleton";
import { RegistryTable } from "./component/RegistryTable";

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
 * The registry read.
 *
 * A server component, so the table is in the first HTML the browser gets and
 * the API never has to be reachable from the visitor's network.
 */
async function RegistryContent({ start }: { start: number }) {
  // The fetch is what can fail, so only the fetch is inside the try. Building
  // JSX in a catch block would not do what it looks like: rendering happens
  // after this function returns, so a render error escapes the handler anyway.
  let result: Awaited<ReturnType<typeof listSkills>> | ApiError;
  try {
    result = await listSkills({ start, limit: PAGE_SIZE });
  } catch (cause) {
    // A read failure is a state to render, not a crash: the visitor should see
    // why the registry is unavailable. Anything that is not an ApiError is a
    // real bug and belongs to the error boundary.
    if (!(cause instanceof ApiError)) throw cause;
    result = cause;
  }

  if (result instanceof ApiError) return <ErrorNotice error={result} />;

  return (
    <>
      <RegistryTable skills={result.skills} />
      <RegistryPagination
        start={result.start}
        limit={result.limit}
        total={result.total}
      />
    </>
  );
}

export function Registry({ start }: { start: string | string[] | undefined }) {
  const offset = parseStart(start);

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      {/* No hero. The pitch belongs on the landing page (STE-23); this route is
          the tool, and a tool should open on its data. */}
      <section>
        <h2 className="mb-6 text-lg font-bold tracking-wider">
          Registry Browser
        </h2>
        {/* Keyed by offset so paging swaps the skeleton back in rather than
            holding the previous page's rows during a ten second read. */}
        <Suspense key={offset} fallback={<RegistrySkeleton />}>
          <RegistryContent start={offset} />
        </Suspense>
      </section>
    </div>
  );
}
