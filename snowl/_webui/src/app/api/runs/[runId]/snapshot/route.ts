import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: { runId: string } }) {
  const store = getMonitorStore();
  const row = store.runSnapshot(context.params.runId);
  if (!row) {
    return NextResponse.json({ detail: `run not found: ${context.params.runId}` }, { status: 404 });
  }
  return NextResponse.json(row);
}
