import { NextRequest, NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> },
) {
  const { runId } = await params;
  const searchParams = request.nextUrl.searchParams;
  const format = searchParams.get("format") || "json";
  const trialKey = searchParams.get("trial_key") || undefined;

  const store = getMonitorStore();
  if (!store) {
    return NextResponse.json({ detail: "Monitor not initialized" }, { status: 503 });
  }

  try {
    const data = store.exportTrials({ runId, trialKey, format });
    const filename = trialKey
      ? `trace_${runId}_${trialKey.replace(/:/g, "_")}.json`
      : `trials_${runId}.json`;

    return new NextResponse(data, {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Content-Disposition": `attachment; filename="${filename}"`,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Export failed";
    return NextResponse.json({ detail: message }, { status: 500 });
  }
}
