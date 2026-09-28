/**
 * A placeholder that sweeps rather than pulses.
 *
 * The dashboard's shadcn Skeleton is the original; this is the same behaviour
 * without pulling shadcn and `cn` into a one-page app. The sweep is a
 * pseudo-element translated across the block, so the block's own size and
 * colour are untouched, and anyone who asked the OS to reduce motion gets the
 * static block with no animation at all.
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`relative overflow-hidden rounded-md bg-elevated before:absolute before:inset-0 before:-translate-x-full before:animate-shimmer before:bg-linear-to-r before:from-transparent before:via-text/10 before:to-transparent motion-reduce:before:hidden ${className}`}
    />
  );
}
