import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CopyHash } from "@/components/copy-hash";
import { EvidenceLinks } from "@/components/evidence-links";
import { RegistryError } from "@/components/registry-states";
import { VerdictBadge } from "@/components/verdict-badge";
import { VerdictBanner } from "@/components/verdict-banner";
import { ApiError, getSkill } from "@/lib/api/client";
import type { AuditedVersion, SkillDetail, Verdict } from "@/lib/api/types";

function formatTimestamp(seconds: number): string {
  return new Date(seconds * 1000).toISOString().replace("T", " ").slice(0, 19);
}

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
  skill: SkillDetail,
): Array<{ version: string; audited: AuditedVersion | null }> {
  const audited = new Map(skill.audited_versions.map((v) => [v.version, v]));
  return skill.versions
    .map((version) => ({ version, audited: audited.get(version) ?? null }))
    .reverse(); // newest first: registration order runs oldest to newest
}

function VersionCard({
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
            {audited ? formatTimestamp(audited.audited_at) : "never"}
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

function SkillView({ skill }: { skill: SkillDetail }) {
  const rows = versionRows(skill);
  const latest = rows[0];
  const latestVerdict: Verdict = latest?.audited?.verdict ?? "UNAUDITED";

  return (
    <>
      <header className="mb-8">
        <h2 className="numeric font-mono text-2xl font-bold break-all">
          {skill.skill_id}
        </h2>
        <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-2 text-sm text-text-secondary">
          <div className="flex gap-2">
            <dt>Owner</dt>
            <dd className="numeric font-mono text-xs break-all text-text">
              {skill.owner}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt>Registered</dt>
            <dd className="numeric font-mono text-xs text-text">
              {formatTimestamp(skill.registered_at)}
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
    </>
  );
}

export default async function SkillPage({
  params,
}: PageProps<"/skills/[skillId]">) {
  const { skillId } = await params;

  // Awaited here rather than inside a Suspense boundary, deliberately.
  // Streaming a shell first would flush a 200 before the API answers, so an
  // unregistered skill would come back 200 with "not registered" in the body.
  // For a service whose whole job is saying whether something is known, an
  // automated client must get a real 404. The detail endpoint answers in about
  // a second, so there is little streaming to give up.
  let skill: SkillDetail | ApiError;
  try {
    skill = await getSkill(decodeURIComponent(skillId));
  } catch (cause) {
    if (!(cause instanceof ApiError)) throw cause;
    // An unknown skill is a 404 page, not an error panel: nothing failed.
    if (cause.isNotFound) notFound();
    skill = cause;
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <Link
        href="/"
        className="mb-8 inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-keyword"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Registry
      </Link>
      {skill instanceof ApiError ? (
        <RegistryError error={skill} />
      ) : (
        <SkillView skill={skill} />
      )}
    </div>
  );
}
