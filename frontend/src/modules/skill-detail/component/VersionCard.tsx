import { VerdictBadge } from "@/components/elements/VerdictBadge";
import type { AuditedVersion, Verdict } from "@/lib/types";
import { formatLedgerTime } from "@/utils/format";
import { CopyHash } from "./CopyHash";
import { EvidenceLinks } from "./EvidenceLinks";

export function VersionCard({
  version,
  audited,
  isLatest,
}: {
  version: string;
  audited: AuditedVersion | null;
  isLatest: boolean;
}) {
  const verdict: Verdict = audited?.verdict ?? "UNAUDITED";

  return (
    <article className="rounded-lg border border-border p-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h3 className="numeric font-mono text-base font-bold">{version}</h3>
          {isLatest ? (
            <span className="rounded-4xl border border-border px-2 py-0.5 text-xs text-text-secondary">
              latest
            </span>
          ) : null}
          <VerdictBadge verdict={verdict} />
        </div>
        <p className="numeric text-sm text-text-secondary">
          {audited ? `Trust ${audited.trust_score}/100` : "No trust score"}
        </p>
      </header>

      <dl className="mt-4 flex flex-wrap gap-x-10 gap-y-3">
        <div>
          <dt className="text-xs text-text-tertiary">Content hash</dt>
          <dd className="mt-1">
            {audited ? (
              <CopyHash value={audited.content_hash} />
            ) : (
              // The hash of an unaudited version is not in this response; it
              // would need a per-version call. Rather than fetch one read per
              // version against an API that already costs 0.44s a row, the
              // page says where it is instead of implying it does not exist.
              <span className="text-xs text-text-tertiary">
                served by GET /check/{version}
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-text-tertiary">Audited at</dt>
          <dd className="numeric mt-1 font-mono text-xs">
            {audited ? formatLedgerTime(audited.audited_at) : "never"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-text-tertiary">Verified badge</dt>
          <dd className="numeric mt-1 font-mono text-xs">
            {audited?.is_verified ? "yes" : "no"}
          </dd>
        </div>
      </dl>

      {audited ? (
        <div className="mt-4">
          <EvidenceLinks evidence={audited.evidence} />
        </div>
      ) : null}
    </article>
  );
}
