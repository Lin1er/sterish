import type { SkillArtifact } from "./types";

/**
 * Save what `GET /use` delivered as one JSON file, path to text.
 *
 * Shared by the licence panel on a version card and the licences page, which
 * both hand a buyer the skill they hold.
 */
export function downloadArtifact(
  skillId: string,
  version: string,
  artifact: SkillArtifact,
): void {
  const blob = new Blob([JSON.stringify(artifact, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${skillId}@${version}.json`;
  link.click();
  URL.revokeObjectURL(url);
}
