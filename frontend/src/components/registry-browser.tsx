import { AlertTriangle, PackageSearch } from "lucide-react";
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
import { VerdictBadge } from "@/components/verdict-badge";
import { hasUnauditedLatest, type SkillListItem } from "@/lib/api/types";

/**
 * The registry table.
 *
 * Presentational on purpose: it takes rows and renders them, so the same
 * component serves live chain data, the mock, and any future filtered view in
 * STE-20 without learning where its data came from.
 *
 * The column that matters most is not the verdict, it is "Audited version".
 * A verdict belongs to one version, so a row whose newest version was never
 * audited must not read as endorsed. That inheritance was the scaffold bug
 * STE-5 removed from the contract, and it would be just as wrong here.
 */
export function RegistryBrowser({ skills }: { skills: SkillListItem[] }) {
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
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Skill ID</TableHead>
            <TableHead>Verdict</TableHead>
            <TableHead className="text-right">Trust score</TableHead>
            <TableHead className="text-right">Latest</TableHead>
            <TableHead className="text-right">Audited</TableHead>
            <TableHead className="text-right">Versions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {skills.map((skill) => {
            const stale = hasUnauditedLatest(skill);
            return (
              // The whole row is the target, not just the id. The link itself
              // stays a real anchor on the skill id, so keyboard focus and
              // screen readers get one sensible link with a readable name, and
              // its ::after is stretched over the row to catch a click
              // anywhere. A row-wide onClick would have needed a client
              // component and would have broken opening in a new tab.
              <TableRow
                key={skill.skill_id}
                className="relative cursor-pointer transition-colors hover:bg-elevated focus-within:bg-elevated"
              >
                <TableCell className="numeric font-mono text-xs">
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
                  {skill.latest_audited_trust_score === null
                    ? "-"
                    : `${skill.latest_audited_trust_score}/100`}
                </TableCell>
                <TableCell className="numeric text-right font-mono text-xs">
                  {skill.latest_version}
                </TableCell>
                <TableCell className="numeric text-right font-mono text-xs">
                  {skill.latest_audited_version === null ? (
                    <span className="text-text-tertiary">never</span>
                  ) : stale ? (
                    <span
                      className="inline-flex items-center gap-1 text-warning"
                      title={`The verdict applies to ${skill.latest_audited_version}, not to the latest version ${skill.latest_version}`}
                    >
                      <AlertTriangle className="size-3" aria-hidden />
                      {skill.latest_audited_version}
                    </span>
                  ) : (
                    skill.latest_audited_version
                  )}
                </TableCell>
                <TableCell className="numeric text-right">
                  {skill.version_count}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

export default RegistryBrowser;
