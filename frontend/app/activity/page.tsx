import type { Metadata } from "next";

import { Activity } from "@/modules/activity/Activity";

export const metadata: Metadata = {
  title: "Audit feed",
  description:
    "Registry activity as the indexer sees it: skills registered, versions published, and verdicts written.",
};

export default function ActivityPage() {
  return <Activity />;
}
