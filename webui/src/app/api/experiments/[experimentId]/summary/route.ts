import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";

export async function GET(request: Request, context: { params: { experimentId: string } }) {
  const store = getMonitorStore();
  const url = new URL(request.url);
  const view = url.searchParams.get("view") || "agent-first";
  const summary = store.experimentSummary({
    experimentId: context.params.experimentId,
    primaryDimension: view,
  });
  return NextResponse.json(summary);
}
