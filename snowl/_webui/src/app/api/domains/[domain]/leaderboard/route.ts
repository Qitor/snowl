import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: { domain: string } }) {
  const store = getMonitorStore();
  const url = new URL(request.url);
  const benchmarkType = url.searchParams.get("type") || undefined;
  const rows = store.domainLeaderboard(context.params.domain, benchmarkType);
  return NextResponse.json({ items: rows });
}
