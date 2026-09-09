import { ExternalLink } from "lucide-react";

import { CopyHash } from "@/modules/skill-detail/component/CopyHash";
import type { Evidence } from "@/lib/types";

/**
 * The transactions behind a verdict.
 *
 * Spec section 2: a verdict without a link to the transaction that wrote it is
 * an unverifiable claim, which is the thing this product exists to eliminate.
 * So every row here is rendered even when the value is missing, and a missing
 * value says so rather than disappearing. A quietly absent audit link looks
 * exactly like a verdict nobody can check.
 */
function Row({
  label,
  href,
  children,
  missing,
}: {
  label: string;
  href?: string | null;
  children?: React.ReactNode;
  missing?: string;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-border py-2.5 last:border-b-0">
      <dt className="text-sm text-text-secondary">{label}</dt>
      <dd className="text-sm">
        {children ??
          (href ? (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="numeric inline-flex items-center gap-1 font-mono text-xs text-keyword hover:underline"
            >
              {href.split("/").pop()?.slice(0, 16)}...
              <ExternalLink className="size-3" aria-hidden />
            </a>
          ) : (
            <span className="text-xs text-text-tertiary">{missing}</span>
          ))}
      </dd>
    </div>
  );
}

export function EvidenceLinks({ evidence }: { evidence: Evidence }) {
  return (
    <dl className="rounded-lg border border-border bg-surface px-4 py-1">
      <Row
        label="Registry contract"
        href={evidence.contract_url}
        missing="not configured"
      />
      <Row
        label="Registration transaction"
        href={evidence.registration_tx_url}
        missing="not indexed yet"
      />
      <Row
        label="Audit transaction"
        href={evidence.audit_tx_url}
        missing="none, this version was never audited"
      />
      <Row label="Evidence hash">
        {evidence.evidence_hash ? (
          <CopyHash value={evidence.evidence_hash} chars={8} />
        ) : (
          <span className="text-xs text-text-tertiary">
            none, this version was never audited
          </span>
        )}
      </Row>
      <Row label="Findings report">
        {evidence.report_uri ? (
          <a
            href={evidence.report_uri}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-keyword hover:underline"
          >
            Open the report
            <ExternalLink className="size-3" aria-hidden />
          </a>
        ) : (
          // GET /reports is still PLANNED in the spec and the live API serves
          // report_uri as null for every version. Saying so is better than an
          // empty cell that reads like an oversight, and far better than
          // linking somewhere that would 404.
          <span className="text-xs text-text-tertiary">
            not published yet
          </span>
        )}
      </Row>
    </dl>
  );
}
