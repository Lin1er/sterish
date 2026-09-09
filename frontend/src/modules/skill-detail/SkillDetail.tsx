import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ErrorNotice } from "@/components/elements/ErrorNotice";
import { ApiError, getSkill } from "@/lib/api";
import type { AuditedVersion, SkillDetail as Skill, Verdict } from "@/lib/types";
import { formatLedgerTime } from "@/utils/format";
import { AuditTrail } from "./component/AuditTrail";
import { TrustScorePanel } from "./component/TrustScorePanel";
import { VerdictBanner } from "./component/VerdictBanner";
import { VersionCard } from "./component/VersionCard";

/**
 * One row per registered version, audited or not.
 *
 * `audited_versions` only carries versions that received a verdict, so the
 * unaudited ones are reconstructed from `versions`. They are shown rather than
 * hidden: a version list that silently omits the unaudited ones would make the
 * newest release invisible, which is precisely the release somebody is about to
 * install.
 */
function versionRows(
  skill: Skill,
): Array<{ version: string; audited: AuditedVersion | null }> {
  const audited = new Map(skill.audited_versions.map((v) => [v.version, v]));
  return skill.versions
    .map((version) => ({ version, audited: audited.get(version) ?? null }))
    .reverse(); // newest first: registration order runs oldest to newest
}

function SkillBody({ skill }: { skill: Skill }) {
  const rows = versionRows(skill);
  const latest = rows[0];
  const latestVerdict: Verdict = latest?.audited?.verdict ?? "UNAUDITED";

  return (
    <>
      <header className="mb-8">
        <h2 className="numeric font-mono text-2xl font-bold break-all">
          {skill.skill_id}
        </h2>
        {/* items-baseline, not the default stretch. Each row pairs a text-sm
            label with a font-mono text-xs value, and two different font sizes
            in a flex row only line up if they are aligned on their baseline. */}
        <dl className="mt-3 flex flex-wrap items-baseline gap-x-8 gap-y-2 text-sm text-text-secondary">
          <div className="flex items-baseline gap-2">
            <dt>Owner</dt>
            <dd className="numeric font-mono text-xs break-all text-text">
              {skill.owner}
            </dd>
          </div>
          <div className="flex items-baseline gap-2">
            <dt>Registered</dt>
            <dd className="numeric font-mono text-xs text-text">
              {formatLedgerTime(skill.registered_at)}
            </dd>
          </div>
        </dl>
      </header>

      {/* The banner describes the version somebody would install today, which
          is the latest one, not the one that happens to have the best verdict. */}
      {latest ? (
        <VerdictBanner
          verdict={latestVerdict}
          version={latest.version}
          trustScore={latest.audited?.trust_score ?? null}
        />
      ) : null}

      {skill.warning ? (
        <p className="mt-3 rounded-lg border border-warning-border bg-warning-surface px-4 py-3 text-sm text-warning">
          {skill.warning}
        </p>
      ) : null}

      <h3 className="mt-10 mb-4 text-lg font-bold tracking-wider">
        Versions
        <span className="ml-2 text-sm font-normal text-text-secondary">
          {skill.versions.length} registered, {skill.audited_versions.length}{" "}
          audited
        </span>
      </h3>

      <div className="space-y-4">
        {rows.map((row) => (
          <VersionCard
            key={row.version}
            version={row.version}
            audited={row.audited}
            isLatest={row.version === skill.latest_version}
          />
        ))}
      </div>

      {/* Only for a version that actually has a score. An unaudited version has
          no number to explain, and a zero rendered as a bar would read as a
          very low score rather than the absence of one. */}
      {latest?.audited ? (
        <TrustScorePanel
          score={latest.audited.trust_score}
          auditTxUrl={latest.audited.evidence.audit_tx_url}
        />
      ) : null}

      <AuditTrail skillId={skill.skill_id} />
    </>
  );
}

export async function SkillDetail({ skillId }: { skillId: string }) {
  // Awaited without a Suspense boundary, deliberately. Streaming a shell first
  // would flush a 200 before the API answers, so an unregistered skill would
  // come back 200 with "not registered" in the body. For a service whose whole
  // job is saying whether something is known, an automated client must get a
  // real 404. The detail endpoint answers in about a second, so there is little
  // streaming to give up.
  let skill: Skill | ApiError;
  try {
    skill = await getSkill(skillId);
  } catch (cause) {
    if (!(cause instanceof ApiError)) throw cause;
    // An unknown skill is a 404 page, not an error panel: nothing failed.
    if (cause.isNotFound) notFound();
    skill = cause;
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
      <Link
        href="/"
        className="mb-8 inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-keyword"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Registry
      </Link>
      {skill instanceof ApiError ? (
        <ErrorNotice error={skill} />
      ) : (
        <SkillBody skill={skill} />
      )}
    </div>
  );
}
