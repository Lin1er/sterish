import { AlertTriangle, ChevronRight, PackageSearch } from "lucide-react";
import Link from "next/link";

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { VerdictBadge } from "@/components/elements/VerdictBadge";
import { hasUnauditedLatest, type SkillListItem } from "@/lib/types";

/**
 * "Audited 0.9.0" with a warning when that is not the latest version.
 *
 * Shared by both layouts because it carries the column that matters most: a
 * verdict belongs to one version, so a skill whose newest release was never
 * audited must not read as endorsed. That was the scaffold bug STE-5 removed
 * from the contract, and it would be just as wrong here.
 */
function AuditedVersionCell({ skill }: { skill: SkillListItem }) {
  if (skill.latest_audited_version === null) {
    return <span className="text-text-tertiary">never</span>;
  }
  if (!hasUnauditedLatest(skill)) return <>{skill.latest_audited_version}</>;
  return (
    <span
      className="inline-flex items-center gap-1 text-warning"
      title={`The verdict applies to ${skill.latest_audited_version}, not to the latest version ${skill.latest_version}`}
    >
      <AlertTriangle className="size-3" aria-hidden />
      {skill.latest_audited_version}
    </span>
  );
}

function trustLabel(skill: SkillListItem): string {
  return skill.latest_audited_trust_score === null
    ? "-"
    : `${skill.latest_audited_trust_score}/100`;
}

/**
 * One skill as a card, for phones.
 *
 * A six column table on a 390px screen can only be made to fit by scrolling it
 * sideways, and a table you have to drag is a table nobody reads the right
 * hand side of. The right hand side here is the audited version, which is the
 * whole point. So on a phone the same fields are stacked instead, and nothing
 * is dropped.
 */
function SkillCard({ skill }: { skill: SkillListItem }) {
  return (
    // Touch has no hover, so a tappable card has to look tappable standing
    // still. The chevron is the affordance, and active: gives the press
    // something to answer with. A separate "view" button was the alternative
    // and was rejected: it would compete with the card itself, which is
    // already one big link.
    <li className="relative cursor-pointer rounded-lg border border-border p-4 transition-colors hover:bg-elevated focus-within:bg-elevated active:bg-elevated">
      <div className="flex items-start justify-between gap-3">
        <Link
          href={`/skills/${encodeURIComponent(skill.skill_id)}`}
          className="numeric font-mono text-xs break-all after:absolute after:inset-0 after:content-[''] hover:text-keyword"
        >
          {skill.skill_id}
        </Link>
        <div className="flex shrink-0 items-center gap-1.5">
          <VerdictBadge verdict={skill.latest_audited_verdict ?? "UNAUDITED"} />
          <ChevronRight
            className="size-4 text-text-tertiary"
            aria-hidden
          />
        </div>
      </div>
      <dl className="numeric mt-3 flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-text-secondary">
        <div className="flex gap-1.5">
          <dt className="text-text-tertiary">Trust</dt>
          <dd>{trustLabel(skill)}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-text-tertiary">Latest</dt>
          <dd>{skill.latest_version}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-text-tertiary">Audited</dt>
          <dd>
            <AuditedVersionCell skill={skill} />
          </dd>
        </div>
      </dl>
    </li>
  );
}

/**
 * The registry.
 *
 * Presentational on purpose: it takes rows and renders them, so the same
 * component serves live chain data, the mock, and any future filtered view
 * without learning where its data came from.
 */
export function RegistryTable({ skills }: { skills: SkillListItem[] }) {
  if (skills.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <PackageSearch />
          </EmptyMedia>
          <EmptyTitle>No skills registered yet</EmptyTitle>
          <EmptyDescription>
            The registry answered, and it is empty. Once a skill is registered
            on chain it appears here.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <>
      <ul className="space-y-2 sm:hidden">
        {skills.map((skill) => (
          <SkillCard key={skill.skill_id} skill={skill} />
        ))}
      </ul>

      <div className="hidden sm:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Skill ID</TableHead>
              <TableHead>Verdict</TableHead>
              <TableHead className="text-right">Trust score</TableHead>
              <TableHead className="text-right">Latest</TableHead>
              <TableHead className="text-right">Audited</TableHead>
              <TableHead className="hidden text-right md:table-cell">
                Versions
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {skills.map((skill) => (
              // The whole row is the target, not just the id. The link stays a
              // real anchor on the skill id, so keyboard focus and screen
              // readers get one link with a readable name, and its ::after is
              // stretched over the row to catch a click anywhere. A row-wide
              // onClick would have needed a client component and would have
              // broken opening in a new tab.
              <TableRow
                key={skill.skill_id}
                className="relative cursor-pointer transition-colors hover:bg-elevated focus-within:bg-elevated"
              >
                <TableCell className="numeric max-w-[38vw] truncate font-mono text-xs lg:max-w-none">
                  <Link
                    href={`/skills/${encodeURIComponent(skill.skill_id)}`}
                    className="after:absolute after:inset-0 after:content-[''] hover:text-keyword"
                  >
                    {skill.skill_id}
                  </Link>
                </TableCell>
                <TableCell>
                  {/* A skill with no audited version at all is UNAUDITED, which
                      the badge renders as its own state. Rule 4 of the API
                      spec: UNAUDITED is never a soft SAFE. */}
                  <VerdictBadge
                    verdict={skill.latest_audited_verdict ?? "UNAUDITED"}
                  />
                </TableCell>
                <TableCell className="numeric text-right">
                  {trustLabel(skill)}
                </TableCell>
                <TableCell className="numeric text-right font-mono text-xs">
                  {skill.latest_version}
                </TableCell>
                <TableCell className="numeric text-right font-mono text-xs">
                  <AuditedVersionCell skill={skill} />
                </TableCell>
                <TableCell className="numeric hidden text-right md:table-cell">
                  {skill.version_count}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}

export default RegistryTable;
