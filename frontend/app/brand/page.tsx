import type { Metadata } from "next";

import { Brand } from "@/modules/brand/Brand";

export const metadata: Metadata = {
  title: "Design tokens",
  description:
    "The living reference for the Sterish palette, verdict colours, typography and radii — read from the real tokens, with contrast recomputed in the browser.",
};

export default function BrandPage() {
  return <Brand />;
}
