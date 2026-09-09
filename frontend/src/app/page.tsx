import { Suspense } from "react";

import { RegistryBrowser } from "@/components/registry-browser";
import { RegistryPagination } from "@/components/registry-pagination";
import { RegistryError, RegistrySkeleton } from "@/components/registry-states";
import { ApiError, listSkills } from "@/lib/api/client";

/**
 * 20, not the 50 the spec allows. GET /skills costs about 0.44s per row
 * against the live API, so 50 rows is a 22 second wait. Paging is the
 * compromise until that fan-out is batched.
 */
const PAGE_SIZE = 20;

/**
 * The registry read.
 *
 * A server component, so the table is in the first HTML the browser gets and
 * the API never has to be reachable from the visitor's network. Wrapped in
 * Suspense below, which streams the skeleton while this awaits.
 */
async function RegistryTable({ start }: { start: number }) {
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

  if (result instanceof ApiError) return <RegistryError error={result} />;

  return (
    <>
      <RegistryBrowser skills={result.skills} />
      <RegistryPagination
        start={result.start}
        limit={result.limit}
        total={result.total}
      />
    </>
  );
}

export default async function Home({ searchParams }: PageProps<"/">) {
  const { start } = await searchParams;
  // A hand-edited query string is user input. Anything that is not a
  // non-negative integer falls back to the first page rather than being passed
  // through to the API to be rejected there.
  const parsed = Number(Array.isArray(start) ? start[0] : start);
  const offset = Number.isInteger(parsed) && parsed >= 0 ? parsed : 0;

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <section className="mb-16 text-center">
        <h2 className="text-4xl font-extrabold tracking-tight">
          Audited Skills for <span className="text-keyword">AI Agents</span>
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-text-secondary">
          On-chain registry with multi-stage LLM audit, trust scoring, and a
          USDC licence an agent buys once per skill version, built on Stellar.
        </p>
      </section>

      <section>
        <h3 className="mb-6 text-lg font-bold tracking-wider">
          Registry Browser
        </h3>
        <Suspense key={offset} fallback={<RegistrySkeleton />}>
          <RegistryTable start={offset} />
        </Suspense>
      </section>
    </div>
  );
}
