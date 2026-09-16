import { cn } from "cn"

/**
 * A placeholder with a shimmer rather than shadcn's default pulse.
 *
 * The sweep is a pseudo-element translated across the block, so the block's own
 * size and colour are untouched and every existing `className` keeps working.
 * `overflow-hidden` keeps the band inside rounded corners. Anyone who asked the
 * OS to reduce motion gets the static block and no animation at all.
 */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        "relative overflow-hidden rounded-md bg-muted",
        "before:absolute before:inset-0 before:-translate-x-full before:animate-shimmer before:bg-linear-to-r before:from-transparent before:via-foreground/10 before:to-transparent",
        "motion-reduce:before:hidden",
        className
      )}
      {...props}
    />
  )
}

export { Skeleton }
