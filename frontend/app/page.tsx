import { Registry } from "@/modules/registry/Registry";

export default async function RegistryPage({ searchParams }: PageProps<"/">) {
  const { start } = await searchParams;
  return <Registry start={start} />;
}
