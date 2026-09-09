import Image from "next/image";
import Link from "next/link";

import { WalletButton } from "./WalletButton";

/**
 * No nav links. There is exactly one destination right now, the registry, and
 * the logo already goes there: a nav whose only entry duplicates the logo is
 * furniture. /tokens is a design-token preview kept for the polish pass, not a
 * place to send anyone, and GitHub is provenance, so it sits in the footer.
 * When the audit feed lands in STE-21 there will be a second real destination
 * and a nav will have earned its place.
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
        <WalletButton />
      </div>
    </header>
  );
}
