import { Gauge } from "lucide-react";

/**
 * What the trust score is made of, and what cannot be shown.
 *
 * STE-21 asks for a breakdown of the score's components. That breakdown does
 * not exist to be shown, and this panel says so instead of drawing bars from
 * invented numbers:
 *
 * - The contract's `TrustScoreConfig` names three components, description
 *   analysis, sandbox behaviour and prior reputation, and holds a weight for
 *   each. Those weights are in instance storage and **no endpoint serves
 *   them**, so the actual split cannot be stated here.
 * - The per-component scores are not published anywhere at all.
 *   `verdict.schema.json` defines `score` as a single integer 0 to 100, and
 *   the pipeline submits only that total through `submit_verdict`. Even once
 *   GET /reports lands (STE-32) the report will carry one number, not three.
 *
 * So the honest thing is to name the inputs, point at the transaction that
 * recorded the number, and be explicit that the arithmetic is not public. A
 * fabricated breakdown would be exactly the unverifiable claim this product
 * exists to remove.
 */
export function TrustScorePanel({
  score,
  auditTxUrl,
}: {
  score: number;
  auditTxUrl: string | null;
}) {
  return (
    <section className="mt-10">
      <h3 className="mb-1 flex items-center gap-2 text-lg font-bold tracking-wider">
        <Gauge className="size-4 text-keyword" aria-hidden />
        Trust Score
      </h3>

      <div className="rounded-lg border border-border bg-surface p-5">
        <p className="numeric text-3xl font-bold">
          {score}
          <span className="ml-1 text-base font-normal text-text-tertiary">
            /100
          </span>
        </p>

        {/* A bar, because a number out of 100 is a proportion and reading it as
            one is faster than reading digits. It carries no information the
            number does not, so it is not labelled as if it were a breakdown. */}
        <div
          className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-elevated"
          role="img"
          aria-label={`Trust score ${score} out of 100`}
        >
          <div
            className="h-full rounded-full bg-keyword"
            style={{ width: `${score}%` }}
          />
        </div>

        <p className="mt-4 max-w-2xl text-sm text-text-secondary">
          The registry computes this from three inputs named by the contract:
          description analysis, sandbox behaviour, and prior reputation. Each
          carries a weight held on chain.
        </p>
        <p className="mt-2 max-w-2xl text-sm text-text-secondary">
          The split between them is not shown here because it is not published.
          The weights live in contract instance storage with no endpoint serving
          them, and only the combined total is ever written on chain, so this
          number cannot honestly be broken apart. What can be checked is the
          transaction that recorded it.
        </p>

        {auditTxUrl ? (
          <a
            href={auditTxUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-block text-sm text-keyword hover:underline"
          >
            Open the audit transaction
          </a>
        ) : null}
      </div>
    </section>
  );
}
