import { Suspense } from "react";

import { RegistryBrowser } from "@/components/registry-browser";
import { RegistryError, RegistrySkeleton } from "@/components/registry-states";
import { ApiError, listSkills } from "@/lib/api/client";

/**
 * The registry read.
 *
 * A server component, so the table is in the first HTML the browser gets and
 * the API URL never has to be reachable from the visitor's network. Wrapped in
 * Suspense below, which streams the skeleton while this awaits.
 */
async function RegistryTable() {
  // The fetch is what can fail, so only the fetch is inside the try. Building
  // JSX in a catch block would not do what it looks like: rendering happens
  // after this function returns, so a render error escapes the handler anyway.
  let result: Awaited<ReturnType<typeof listSkills>> | ApiError;
  try {
    // 20, not the 50 the spec allows. GET /skills costs about 0.44s per row
    // against the live API, so 50 would be a 22 second wait for a page whose
    // registry currently holds 20 skills in total. Paging beyond one screen is
    // STE-20's problem, once the API stops reading rows one at a time.
    result = await listSkills({ limit: 20 });
  } catch (cause) {
    // A read failure is a state to render, not a crash: the visitor should see
    // why the registry is unavailable. Anything that is not an ApiError is a
    // real bug and belongs to the error boundary.
    if (!(cause instanceof ApiError)) throw cause;
    result = cause;
  }

  return result instanceof ApiError ? (
    <RegistryError error={result} />
  ) : (
    <RegistryBrowser skills={result.skills} />
  );
}

export default function Home() {
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
        <Suspense fallback={<RegistrySkeleton />}>
          <RegistryTable />
        </Suspense>
      </section>
    </div>
  );
}
