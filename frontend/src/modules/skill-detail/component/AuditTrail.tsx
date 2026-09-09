"use client";

import { History } from "lucide-react";

import { ActivityList } from "@/components/elements/ActivityList";
import { ErrorNotice } from "@/components/elements/ErrorNotice";
import { Skeleton } from "@/components/ui/skeleton";
import { useSkillTrail } from "@/hooks/useSkillTrail";
import { ApiError } from "@/lib/api";

/**
 * What happened to this skill, in order, with a transaction behind every line.
 *
 * This is the "a verdict cannot be changed quietly" evidence. The version cards
 * above say what is true now, read from the chain. The trail says how it got
 * that way: when the skill was registered, when each version was published,
 * and when each verdict was written. A verdict that changed on re-audit would
 * appear here as its own line rather than silently replacing the old one.
 */
export function AuditTrail({ skillId }: { skillId: string }) {
  const { data, error, isPending } = useSkillTrail(skillId);

  return (
    <section className="mt-10">
      <h3 className="mb-1 flex items-center gap-2 text-lg font-bold tracking-wider">
        <History className="size-4 text-keyword" aria-hidden />
        Audit Trail
      </h3>
      <p className="mb-4 text-sm text-text-secondary">
        Indexed registry events for this skill, newest first.
      </p>

      {isPending ? (
        <div className="space-y-2" aria-busy aria-label="Loading the trail">
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-9 w-full" />
          ))}
        </div>
      ) : error ? (
        <TrailError error={error} />
      ) : data.length === 0 ? (
        // The indexer only started at a given ledger, and getEvents scans a
        // bounded window, so an older skill can legitimately have no indexed
        // events. Saying that is better than an empty box implying nothing
        // ever happened to it.
        <p className="rounded-lg border border-border px-4 py-3 text-sm text-text-secondary">
          The indexer has no events for this skill. The verdicts above still
          come from the chain and are unaffected; only this timeline and its
          transaction links depend on the index.
        </p>
      ) : (
        <ActivityList events={data} showSkill={false} />
      )}
    </section>
  );
}

function TrailError({ error }: { error: Error }) {
  // Anything that is not an ApiError is a bug, and the error boundary should
  // see it rather than have it flattened into a tidy notice.
  if (!(error instanceof ApiError)) throw error;
  return <ErrorNotice error={error} />;
}
