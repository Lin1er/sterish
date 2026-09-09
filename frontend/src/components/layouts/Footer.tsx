import { GithubIcon, XIcon } from "@/components/elements/BrandIcons";

/**
 * Provenance, not navigation.
 *
 * The network is named because a visitor has no other way to tell which chain
 * the numbers above came from, and that is the first thing a sceptical reader
 * should be able to check. The links live here rather than in the header for
 * the same reason: they are how somebody follows the project, not a thing they
 * use to get around it.
 */
export function Footer({ network }: { network: string }) {
  return (
    <footer className="mt-16 border-t border-border px-6 py-6">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 text-xs text-text-tertiary">
        <p>
          Reads come straight from the Sterish registry contract on Stellar{" "}
          <span className="text-text-secondary">{network}</span>. Every verdict
          on this site links to the transaction that wrote it.
        </p>
        <nav className="flex items-center gap-5">
          <a
            className="inline-flex items-center gap-1.5 hover:text-keyword"
            href="https://github.com/Lin1er/sterish"
            target="_blank"
            rel="noopener noreferrer"
          >
            <GithubIcon className="size-4" />
            GitHub
          </a>
          <a
            className="inline-flex items-center gap-1.5 hover:text-keyword"
            href="https://x.com/sterishxyz"
            target="_blank"
            rel="noopener noreferrer"
          >
            <XIcon className="size-3.5" />
            X/Twitter
          </a>
        </nav>
      </div>
    </footer>
  );
}
