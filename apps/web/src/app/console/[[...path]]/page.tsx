import { ConsolePage } from "@/modules/console-page";

export default async function Page({
  params
}: {
  params: Promise<{ path?: string[] }>;
}) {
  const { path = [] } = await params;
  return <ConsolePage path={path} />;
}

