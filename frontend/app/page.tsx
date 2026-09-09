import type { Metadata } from "next";

import { Registry } from "@/modules/registry/Registry";

export const metadata: Metadata = {
  // Spelled out rather than left to the layout's template. Next does not apply
  // a title template to a page in the same route segment as the layout that
  // declares it, so this one page would otherwise read just "Registry" while
  // every other page carried the product name.
  title: { absolute: "Registry · Sterish" },
  description:
    "Every skill registered on the Sterish contract, with the audit verdict for the version it applies to.",
};

export default async function RegistryPage({ searchParams }: PageProps<"/">) {
  const { start } = await searchParams;
  return <Registry start={start} />;
}
