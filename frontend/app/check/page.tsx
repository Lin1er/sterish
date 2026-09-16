import type { Metadata } from "next";

import { Check } from "@/modules/check/Check";

export const metadata: Metadata = {
  title: "Check before install",
  description:
    "Hash a skill's files in your browser and look the bytes up on chain before installing it.",
};

export default function CheckPage() {
  return <Check />;
}
