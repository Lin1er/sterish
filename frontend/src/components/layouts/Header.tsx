import Image from "next/image";
import Link from "next/link";

import { NavTabs } from "./NavTabs";
import { WalletButton } from "./WalletButton";

/**
 * The nav is back, and only now.
 *
 * It was removed when the registry was the single destination, because a nav
 * whose only entry duplicates the logo is furniture. The audit feed is a
 * second real place to be, so there is something to navigate between.
 *
 * Still absent on purpose: /tokens is a design-token preview, an internal aid
 * rather than a destination, and the project links are provenance, which is
 * why they sit in the footer.
 */
export function Header() {
  return (
    <header className="border-b border-border px-4 py-3 sm:px-6 sm:py-4">
      {/*
        Two rows on a phone, one row from `sm` up.

        As a single unwrapped row this came to about 460px of logo, links and
        wallet button, which is wider than a 390px phone. A flex row that
        cannot wrap does not overflow quietly: it sets a min-content width on
        the whole document, so every page below was clipped at the same point
        and looked like several separate layout bugs. It was one.
      */}
      <div className="mx-auto max-w-6xl">
        <div className="flex items-center justify-between gap-3">
          <Link href="/" aria-label="Sterish, back to the registry">
            {/* The cream lockup, because the shell is navy. Nabil's export pads
                the artwork inside a 796x400 canvas, so the copy in public/
                keeps his paths untouched and only tightens the viewBox; at
                header size the original would render the wordmark about seven
                pixels tall. */}
            <Image
              src="/brand/logo/sterish-lockup-cream.svg"
              alt="Sterish"
              width={140}
              height={28}
              priority
              className="h-6 w-auto sm:h-7"
            />
          </Link>

          <div className="flex items-center gap-6">
            <NavTabs className="hidden gap-1 sm:flex" />
            <WalletButton />
          </div>
        </div>

        <NavTabs className="mt-2.5 flex gap-1 sm:hidden" />
      </div>
    </header>
  );
}
