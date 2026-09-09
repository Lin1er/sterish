"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import type { MouseEvent } from "react";

/**
 * Offset pagination, because that is what the API offers: `start` and `limit`
 * over a registration-order index, with `total` from the contract's skill
 * count.
 *
 * These stay real `<a href>` elements even though paging is handled in
 * JavaScript. A plain left click is intercepted so the cached page appears
 * instantly, but middle click, ctrl-click and "open in new tab" still work,
 * and the href is still what somebody copies to share page three. Replacing
 * them with buttons would have quietly taken all of that away.
 *
 * There is deliberately no verdict filter or trust-score sort, though the
 * ticket suggested both. The API cannot filter or sort, so either would run on
 * the client over whichever twenty rows this page holds. A control labelled
 * "highest trust first" that only ranks one page out of three is a quiet lie,
 * and this is not a product that can afford quiet lies.
 */
export function RegistryPagination({
  start,
  limit,
  total,
  onNavigate,
  hrefFor,
}: {
  start: number;
  limit: number;
  total: number;
  onNavigate: (start: number) => void;
  hrefFor: (start: number) => string;
}) {
  if (total <= limit) return null;

  const first = start + 1;
  const last = Math.min(start + limit, total);
  const previous = Math.max(0, start - limit);
  const next = start + limit;
  const hasPrevious = start > 0;
  const hasNext = next < total;

  const linkClass =
    "inline-flex cursor-pointer items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm transition-colors hover:border-hairline-strong hover:text-keyword";
  const disabledClass =
    "inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm text-text-tertiary opacity-50";

  /** Let the browser handle anything that is not a plain left click. */
  function handle(target: number) {
    return (event: MouseEvent<HTMLAnchorElement>) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      event.preventDefault();
      onNavigate(target);
    };
  }

  return (
    <nav
      aria-label="Registry pages"
      className="mt-6 flex items-center justify-between gap-4"
    >
      <p className="numeric text-sm text-text-secondary">
        {first} to {last} of {total}
      </p>
      <div className="flex gap-2">
        {hasPrevious ? (
          <a
            href={hrefFor(previous)}
            onClick={handle(previous)}
            className={linkClass}
            rel="prev"
          >
            <ChevronLeft className="size-4" aria-hidden />
            Previous
          </a>
        ) : (
          <span className={disabledClass} aria-disabled>
            <ChevronLeft className="size-4" aria-hidden />
            Previous
          </span>
        )}
        {hasNext ? (
          <a
            href={hrefFor(next)}
            onClick={handle(next)}
            className={linkClass}
            rel="next"
          >
            Next
            <ChevronRight className="size-4" aria-hidden />
          </a>
        ) : (
          <span className={disabledClass} aria-disabled>
            Next
            <ChevronRight className="size-4" aria-hidden />
          </span>
        )}
      </div>
    </nav>
  );
}
