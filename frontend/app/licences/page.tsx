import type { Metadata } from "next";

import { Licences } from "@/modules/licences/Licences";

export const metadata: Metadata = {
  title: "Licences",
  description:
    "Look up every skill licence a Stellar account holds, with the current verdict of each version.",
};

export default function LicencesPage() {
  return <Licences address={null} />;
}
