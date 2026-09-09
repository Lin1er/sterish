import Image from "next/image";
import Link from "next/link";

import { WalletButton } from "./WalletButton";

/**
 * The nav is back, and only now.
 *
 * It was removed when the registry was the single destination, because a nav
 * whose only entry duplicates the logo is furniture. The audit feed is a
 * second real place to be, so there is something to navigate between.
 *
 * Still absent on purpose: /tokens is a design-token preview, an internal aid
 * rather than a destination, and GitHub is provenance, which is why it sits in
 * the footer.
 */
export function Header() {
  return (
    <header className="border-b border-border px-6 py-4">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
        <Link href="/" aria-label="Sterish, back to the registry">
          {/* The cream lockup, because the shell is navy. Nabil's export pads
              the artwork inside a 796x400 canvas, so the copy in public/ keeps
              his paths untouched and only tightens the viewBox; at header size
              the original would render the wordmark about seven pixels tall. */}
          <Image
            src="/brand/logo/sterish-lockup-cream.svg"
            alt="Sterish"
            width={140}
            height={28}
            priority
          />
        </Link>
        <div className="flex items-center gap-6">
          <nav className="flex gap-4 text-sm text-text-secondary">
            <Link className="hover:text-keyword" href="/">
              Registry
            </Link>
            <Link className="hover:text-keyword" href="/activity">
              Audit feed
            </Link>
          </nav>
          <WalletButton />
        </div>
      </div>
    </header>
  );
}
