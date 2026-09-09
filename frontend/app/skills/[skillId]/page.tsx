import type { Metadata } from "next";

import { SkillDetail } from "@/modules/skill-detail/SkillDetail";

/**
 * The skill id is the title.
 *
 * It is the only human-readable name a skill has: the contract stores no name,
 * description or tags, so `com.evil.token-drainer` is the whole identity. It is
 * also taken from the route rather than fetched, which keeps an unregistered
 * skill from paying for a second API call just to title its own 404 page.
 */
export async function generateMetadata({
  params,
}: PageProps<"/skills/[skillId]">): Promise<Metadata> {
  const { skillId } = await params;
  return { title: decodeURIComponent(skillId) };
}

export default async function SkillPage({
  params,
}: PageProps<"/skills/[skillId]">) {
  const { skillId } = await params;
  return <SkillDetail skillId={decodeURIComponent(skillId)} />;
}
