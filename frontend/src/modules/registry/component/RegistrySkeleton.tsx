import { Skeleton } from "@/components/ui/skeleton";

/**
 * The shape of a full page of rows, held while the registry read is in flight.
 *
 * The row count matches the page size on purpose. A short skeleton followed by
 * twenty rows makes the page jump and drags the footer up and down, which is
 * what made the footer look wrong during a fetch. Reserving the real height
 * keeps everything still.
 */
export function RegistrySkeleton({ rows = 20 }: { rows?: number }) {
  return (
    <div aria-busy aria-label="Loading the registry">
      {/* Cards below sm, table rows above, matching what the data renders as. */}
      <div className="space-y-2 sm:hidden">
        {Array.from({ length: rows }, (_, row) => (
          <Skeleton key={row} className="h-24 w-full" />
        ))}
      </div>
      <div className="hidden space-y-2 sm:block">
        <Skeleton className="h-9 w-full" />
        {Array.from({ length: rows }, (_, row) => (
          <Skeleton key={row} className="h-12 w-full" />
        ))}
      </div>
    </div>
  );
}
