import type { Metadata } from "next";

import { Landing } from "@/modules/landing/Landing";

export const metadata: Metadata = {
  title: { absolute: "Sterish — audited skills for AI agents on Stellar" },
  description:
    "Sterish audits AI agent skills and writes the verdict on chain, pinned to the hash of the files it read. Check a specific version before installing it.",
};

export default function LandingPage() {
  return <Landing />;
}
