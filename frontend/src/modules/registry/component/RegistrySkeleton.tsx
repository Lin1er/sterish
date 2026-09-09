import { Skeleton } from "@/components/ui/skeleton";

/**
 * The shape of the table, held while the registry read is in flight.
 *
 * Sized to the real rows rather than a spinner, so the page does not jump when
 * the data lands. That matters more here than usual: GET /skills takes about
 * ten seconds for a full page.
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
