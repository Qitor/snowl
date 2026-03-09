import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const experimentId = url.searchParams.get("experiment_id") || undefined;
  const store = getMonitorStore();
  return NextResponse.json({ items: store.listRuns({ experimentId }) });
}
