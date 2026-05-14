import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: { benchmarkName: string } }) {
  const store = getMonitorStore();
  const detail = store.benchmarkDetail(context.params.benchmarkName);
  if (!detail) {
    return NextResponse.json({ error: "benchmark_not_found" }, { status: 404 });
  }
  return NextResponse.json(detail);
}
