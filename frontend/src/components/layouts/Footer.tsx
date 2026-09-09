import { GithubIcon, XIcon } from "@/components/elements/BrandIcons";

/**
 * Attribution on the left, project links on the right.
 *
 * The network is still named, just as a chip rather than a sentence. A visitor
 * has no other way to tell which chain the numbers above came from, and on a
 * testnet build that is the difference between a demo and a claim about real
 * money.
 */
export function Footer({ network }: { network: string }) {
  const label = `Stellar ${network.charAt(0).toUpperCase()}${network.slice(1)}`;

  return (
    <footer className="mt-16 border-t border-border px-4 py-6 sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-3 text-xs text-text-tertiary">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <p>&copy; {new Date().getFullYear()} Sterish</p>
          <span
            className="inline-flex items-center gap-1.5 rounded-4xl border border-border px-2 py-0.5 text-text-secondary"
            title="Every contract read on this site comes from this network"
          >
            <span className="size-1.5 rounded-full bg-keyword" aria-hidden />
            {label}
          </span>
        </div>
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
