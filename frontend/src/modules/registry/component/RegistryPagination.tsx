import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";

/**
 * Offset pagination, because that is what the API offers: `start` and `limit`
 * over a registration-order index, with `total` from the contract's skill
 * count.
 *
 * There is deliberately no verdict filter or trust-score sort here, though the
 * ticket suggested both. The API cannot filter or sort, so either would have to
 * happen on the client, over whichever twenty rows this page happens to hold.
 * A control labelled "highest trust first" that only ranks one page out of
 * three is a quiet lie, and this is not a product that can afford quiet lies.
 * When the API grows the parameters, both become real in one change here.
 */
export function RegistryPagination({
  start,
  limit,
  total,
}: {
  start: number;
  limit: number;
  total: number;
}) {
  if (total <= limit) return null;

  const first = start + 1;
  const last = Math.min(start + limit, total);
  const previous = Math.max(0, start - limit);
  const next = start + limit;
  const hasPrevious = start > 0;
  const hasNext = next < total;

  const linkClass =
    "inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm transition-colors hover:border-hairline-strong hover:text-keyword";
  const disabledClass =
    "inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm text-text-tertiary opacity-50";

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
          <Link href={`/?start=${previous}`} className={linkClass} rel="prev">
            <ChevronLeft className="size-4" aria-hidden />
            Previous
          </Link>
        ) : (
          <span className={disabledClass} aria-disabled>
            <ChevronLeft className="size-4" aria-hidden />
            Previous
          </span>
        )}
        {hasNext ? (
          <Link href={`/?start=${next}`} className={linkClass} rel="next">
            Next
            <ChevronRight className="size-4" aria-hidden />
          </Link>
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
