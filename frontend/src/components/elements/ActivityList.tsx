import {
  ExternalLink,
  FilePlus2,
  GitBranchPlus,
  ShieldQuestion,
} from "lucide-react";
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
  verdict_flipped: {
    label: "Verdict changed on re-audit",
    icon: ShieldQuestion,
  },
} as const;

function describe(event: string) {
  return (
    EVENT[event as keyof typeof EVENT] ?? { label: event, icon: ShieldQuestion }
  );
}

/**
 * A list of registry events, newest first.
 *
 * Presentational: it renders whatever events it is handed, so the feed page
 * and a single skill's trail are the same component with different data.
 *
 * Two lines on a phone and one line from `sm` up. Six pieces of information on
 * one row is comfortable at desktop width and unreadable at 390px, and the
 * piece that gets squeezed out first is the skill id, which is how you know
 * what the line is about.
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
            className="flex flex-col gap-1 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-3 sm:gap-y-1 sm:py-2.5"
          >
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 sm:flex-nowrap sm:gap-3">
              <Icon
                className="size-4 shrink-0 text-text-tertiary"
                aria-hidden
              />
              <span className="text-sm whitespace-nowrap text-text-secondary">
                {label}
              </span>
              {item.verdict ? <VerdictBadge verdict={item.verdict} /> : null}
              {item.trust_score === null ? null : (
                <span className="numeric text-xs whitespace-nowrap text-text-secondary">
                  {item.trust_score}/100
                </span>
              )}
            </div>

            <div className="flex min-w-0 items-center gap-2 pl-6 sm:contents sm:pl-0">
              {showSkill ? (
                <Link
                  href={`/skills/${encodeURIComponent(item.skill_id)}`}
                  className="numeric min-w-0 truncate font-mono text-xs hover:text-keyword hover:underline"
                >
                  {item.skill_id}
                </Link>
              ) : null}

              {item.version ? (
                <span className="numeric font-mono text-xs whitespace-nowrap text-text-tertiary">
                  {item.version}
                </span>
              ) : null}

              <span className="numeric ml-auto text-xs whitespace-nowrap text-text-tertiary">
                {item.occurred_at === null
                  ? `ledger ${item.ledger}`
                  : formatRelativeTime(item.occurred_at)}
              </span>

              <a
                href={item.tx_url}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0 text-text-tertiary hover:text-keyword"
                aria-label={`Transaction ${item.tx_hash} on stellar.expert`}
              >
                <ExternalLink className="size-3.5" aria-hidden />
              </a>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
