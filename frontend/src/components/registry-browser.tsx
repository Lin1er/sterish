import { PackageSearch } from "lucide-react";

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
import { VerdictBadge, type Verdict } from "@/components/verdict-badge";

interface Skill {
  skill_id: string;
  name: string;
  verdict: Verdict;
  trust_score: number;
  versions: number;
}

export default function RegistryBrowser() {
  // TODO(STE-8): read from the data layer once it lands. Kept empty on purpose
  // rather than seeded with fake rows, so the empty state is the thing under
  // review right now and nobody mistakes a fixture for live registry data.
  const skills: Skill[] = [];

  if (skills.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <PackageSearch />
          </EmptyMedia>
          <EmptyTitle>No skills registered yet</EmptyTitle>
          <EmptyDescription>
            Connect the verification API to load the registry.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Skill ID</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Verdict</TableHead>
          <TableHead className="text-right">Trust score</TableHead>
          <TableHead className="text-right">Versions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {skills.map((s) => (
          <TableRow key={s.skill_id}>
            <TableCell className="numeric font-mono text-xs">
              {s.skill_id}
            </TableCell>
            <TableCell>{s.name}</TableCell>
            <TableCell>
              <VerdictBadge verdict={s.verdict} />
            </TableCell>
            <TableCell className="numeric text-right">
              {s.trust_score}/100
            </TableCell>
            <TableCell className="numeric text-right">{s.versions}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
