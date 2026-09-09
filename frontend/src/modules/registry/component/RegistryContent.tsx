"use client";

import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { ErrorNotice } from "@/components/elements/ErrorNotice";
import { useSkills } from "@/hooks/useSkills";
import { ApiError } from "@/lib/api";
import { RegistryPagination } from "./RegistryPagination";
import { RegistrySkeleton } from "./RegistrySkeleton";
import { RegistryTable } from "./RegistryTable";

function urlFor(start: number): string {
  return start === 0 ? "/" : `/?start=${start}`;
}

function startFromLocation(): number {
  const raw = new URLSearchParams(window.location.search).get("start");
  const value = Number(raw ?? 0);
  return Number.isInteger(value) && value >= 0 ? value : 0;
}

/**
 * The registry table, paged on the client.
 *
 * Paging does not navigate. A `<Link>` would re-run the server component and
 * pay the full ten seconds again for a page the browser already has, which is
 * the whole thing this cache exists to stop. Instead the offset is state, the
 * URL is updated with history.pushState so it stays shareable, and React Query
 * answers a revisited page from memory.
 *
 * The first page still comes from the server: it was prefetched and dehydrated
 * by the module above, so this renders with data on the very first paint rather
 * than flashing a skeleton.
 */
export function RegistryContent({
  initialStart,
  pageSize,
}: {
  initialStart: number;
  pageSize: number;
}) {
  const [start, setStart] = useState(initialStart);
  const { data, error, isPending, isPlaceholderData } = useSkills(
    start,
    pageSize,
  );

  // Back and forward have to keep working. Without this the URL would change
  // under the browser's feet and the button would leave the page showing rows
  // from an offset the address bar no longer names.
  useEffect(() => {
    const onPopState = () => setStart(startFromLocation());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const goTo = useCallback((next: number) => {
    setStart(next);
    window.history.pushState(null, "", urlFor(next));
    window.scrollTo({ top: 0 });
  }, []);

  if (isPending) return <RegistrySkeleton />;

  if (error) {
    // Anything that is not an ApiError is a bug, and the error boundary should
    // see it rather than have it flattened into a tidy notice.
    if (!(error instanceof ApiError)) throw error;
    return <ErrorNotice error={error} />;
  }

  return (
    <>
      {/* While a new page loads, the previous rows stay up rather than being
          replaced by a ten second blank. Dimming alone was not enough: against
          an API that takes ten seconds it just looked like the table had
          broken, so the wait is named as well as shown. */}
      {isPlaceholderData ? (
        <p
          role="status"
          className="mb-3 flex items-center gap-2 text-sm text-text-secondary"
        >
          <Loader2 className="size-4 animate-spin text-keyword" aria-hidden />
          Loading rows {start + 1} to {start + pageSize}. The rows below are the
          previous page, kept until the new ones arrive.
        </p>
      ) : null}
      <div
        className={
          isPlaceholderData ? "opacity-50 transition-opacity" : undefined
        }
        aria-busy={isPlaceholderData}
      >
        <RegistryTable skills={data.skills} />
      </div>
      <RegistryPagination
        start={data.start}
        limit={data.limit}
        total={data.total}
        onNavigate={goTo}
        hrefFor={urlFor}
      />
    </>
  );
}
