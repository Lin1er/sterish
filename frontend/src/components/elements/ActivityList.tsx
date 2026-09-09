import { ExternalLink, FilePlus2, GitBranchPlus, ShieldQuestion } from "lucide-react";
import Link from "next/link";

import { VerdictBadge } from "@/components/elements/VerdictBadge";
import type { FeedEvent } from "@/lib/types";
import { formatRelativeTime } from "@/utils/format";

/**
 * How each indexed event reads to somebody who did not write the contract.
 *
 * The raw event names are contract vocabulary. `version_recorded` in
 * particular is the one that matters, since it is the moment a verdict was
 * written, and calling it "recorded" hides that. Unknown events fall through
 * to their raw name rather than being dropped: a new event type appearing is
 * something to notice, not to swallow.
 */
const EVENT = {
  skill_registered: { label: "Skill registered", icon: FilePlus2 },
  version_registered: { label: "Version published", icon: GitBranchPlus },
  version_recorded: { label: "Audit verdict written", icon: ShieldQuestion },
  verdict_flipped: { label: "Verdict changed on re-audit", icon: ShieldQuestion },
} as const;

function describe(event: string) {
  return (
    EVENT[event as keyof typeof EVENT] ?? { label: event, icon: ShieldQuestion }
  );
}

/**
 * A list of registry events, newest first.
 *
 * Presentational: it renders whatever events it is handed, so the home page
 * feed and a single skill's trail are the same component with different data.
 *
 * Every row carries its transaction link. The feed comes from the indexer,
 * which api-spec section 6 is explicit is a cache and never a source of truth,
 * so the transaction is what makes each line checkable rather than a claim the
 * dashboard is making.
 */
export function ActivityList({
  events,
  showSkill = true,
}: {
  events: FeedEvent[];
  showSkill?: boolean;
}) {
  return (
    <ol className="divide-y divide-border">
      {events.map((item) => {
        const { label, icon: Icon } = describe(item.event);
        return (
          <li
            key={`${item.tx_hash}-${item.event}-${item.version ?? ""}`}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5"
          >
            <Icon className="size-4 shrink-0 text-text-tertiary" aria-hidden />
            <span className="text-sm text-text-secondary">{label}</span>

            {showSkill ? (
              <Link
                href={`/skills/${encodeURIComponent(item.skill_id)}`}
                className="numeric font-mono text-xs hover:text-keyword hover:underline"
              >
                {item.skill_id}
              </Link>
            ) : null}

            {item.version ? (
              <span className="numeric font-mono text-xs text-text-tertiary">
                {item.version}
              </span>
            ) : null}

            {item.verdict ? <VerdictBadge verdict={item.verdict} /> : null}

            {item.trust_score === null ? null : (
              <span className="numeric text-xs text-text-secondary">
                {item.trust_score}/100
              </span>
            )}

            <span className="numeric ml-auto text-xs text-text-tertiary">
              {item.occurred_at === null
                ? `ledger ${item.ledger}`
                : formatRelativeTime(item.occurred_at)}
            </span>

            <a
              href={item.tx_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-text-tertiary hover:text-keyword"
              aria-label={`Transaction ${item.tx_hash} on stellar.expert`}
            >
              <ExternalLink className="size-3.5" aria-hidden />
            </a>
          </li>
        );
      })}
    </ol>
  );
}
