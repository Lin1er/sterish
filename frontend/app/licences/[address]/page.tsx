import type { Metadata } from "next";

import { Licences } from "@/modules/licences/Licences";

export async function generateMetadata({
  params,
}: PageProps<"/licences/[address]">): Promise<Metadata> {
  const { address } = await params;
  const decoded = decodeURIComponent(address);
  return { title: `Licences of ${decoded.slice(0, 4)}...${decoded.slice(-4)}` };
}

export default async function AddressLicencesPage({
  params,
}: PageProps<"/licences/[address]">) {
  const { address } = await params;
  return <Licences address={decodeURIComponent(address).trim()} />;
}
