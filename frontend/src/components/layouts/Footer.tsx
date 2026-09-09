/**
 * Provenance, not navigation.
 *
 * The network is named because a visitor has no other way to tell which chain
 * the numbers above came from, and that is the first thing a sceptical reader
 * should be able to check. GitHub lives here rather than in the header for the
 * same reason: it is how somebody verifies the claims, not a thing they use.
 */
export function Footer({ network }: { network: string }) {
  return (
    <footer className="mt-16 border-t border-border px-6 py-6">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 text-xs text-text-tertiary">
        <p>
          Reads come straight from the Sterish registry contract on Stellar{" "}
          <span className="text-text-secondary">{network}</span>. Every verdict
          on this site links to the transaction that wrote it.
        </p>
        <a
          className="hover:text-keyword"
          href="https://github.com/Lin1er/sterish"
          target="_blank"
          rel="noopener noreferrer"
        >
          Source on GitHub
        </a>
      </div>
    </footer>
  );
}
