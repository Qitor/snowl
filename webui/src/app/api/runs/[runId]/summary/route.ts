import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: { runId: string } }) {
  const store = getMonitorStore();
  const url = new URL(request.url);
  const view = url.searchParams.get("view") || "variant-first";
  const summary = store.runSummary({
    runId: context.params.runId,
    primaryDimension: view,
  });
  if (!summary) {
    return NextResponse.json({ detail: `run not found: ${context.params.runId}` }, { status: 404 });
  }
  return NextResponse.json(summary);
}
