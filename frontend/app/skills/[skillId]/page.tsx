import { SkillDetail } from "@/modules/skill-detail/SkillDetail";

export default async function SkillPage({
  params,
}: PageProps<"/skills/[skillId]">) {
  const { skillId } = await params;
  return <SkillDetail skillId={decodeURIComponent(skillId)} />;
}
