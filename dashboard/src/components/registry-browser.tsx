interface Skill {
  skill_id: string;
  name: string;
  verdict: 'UNAUDITED' | 'SAFE' | 'DANGEROUS' | 'WARNING';
  trust_score: number;
  versions: number;
}

const verdictColor: Record<string, string> = {
  SAFE: 'text-[var(--color-safe)]',
  WARNING: 'text-[var(--color-warning)]',
  DANGEROUS: 'text-[var(--color-danger)]',
  UNAUDITED: 'text-[var(--color-muted)]',
};

export default function RegistryBrowser() {
  // TODO: fetch from /api/skills once connected
  const skills: Skill[] = [];

  if (skills.length === 0) {
    return (
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center text-[var(--color-muted)]">
        No skills registered yet. Connect the API to load the registry.
      </div>
    );
  }

  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-[var(--color-border)] text-[var(--color-muted)]">
          <th className="pb-3 font-medium">Skill ID</th>
          <th className="pb-3 font-medium">Name</th>
          <th className="pb-3 font-medium">Verdict</th>
          <th className="pb-3 font-medium">Trust Score</th>
          <th className="pb-3 font-medium">Versions</th>
        </tr>
      </thead>
      <tbody>
        {skills.map((s) => (
          <tr
            key={s.skill_id}
            className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface)]"
          >
            <td className="py-3 font-mono text-xs">{s.skill_id}</td>
            <td className="py-3">{s.name}</td>
            <td className={`py-3 font-medium ${verdictColor[s.verdict]}`}>
              {s.verdict}
            </td>
            <td className="py-3">{s.trust_score}/100</td>
            <td className="py-3">{s.versions}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
