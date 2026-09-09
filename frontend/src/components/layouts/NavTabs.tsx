"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const DESTINATIONS = [
  { href: "/", label: "Registry" },
  { href: "/activity", label: "Audit feed" },
];

/**
 * Top-level destinations, as tabs.
 *
 * Tabs rather than a bottom navigation bar, which was the alternative. There
 * are two destinations today and STE-22 adds a third; a fixed bar for that is
 * a lot of permanent screen furniture, and it would sit on top of the footer,
 * where the network chip lives. That chip is the only thing telling a visitor
 * these numbers come from testnet, so covering it is the one thing the layout
 * should not do. If this ever reaches five destinations, revisit.
 *
 * The active tab is marked with a filled pill rather than colour alone, so it
 * survives greyscale and does not rely on the accent being distinguishable.
 */
export function NavTabs({ className }: { className?: string }) {
  const pathname = usePathname();

  return (
    <nav className={className} aria-label="Sections">
      {DESTINATIONS.map(({ href, label }) => {
        // A skill page belongs to the registry: /skills/... should not leave
        // both tabs looking inactive.
        const active =
          href === "/"
            ? pathname === "/" || pathname.startsWith("/skills")
            : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={
              active
                ? "rounded-4xl bg-elevated px-3 py-1 text-sm whitespace-nowrap text-text"
                : "rounded-4xl px-3 py-1 text-sm whitespace-nowrap text-text-secondary transition-colors hover:bg-elevated/60 hover:text-text"
            }
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
