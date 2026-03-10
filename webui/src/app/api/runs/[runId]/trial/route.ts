import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: { runId: string } }) {
  const url = new URL(request.url);
  const trialKey = (url.searchParams.get("trial_key") || "").trim();
  if (!trialKey) {
    return NextResponse.json({ detail: "trial_key is required" }, { status: 400 });
  }
  const store = getMonitorStore();
  const item = store.getTrialDetails({ runId: context.params.runId, trialKey });
  if (!item) {
    return NextResponse.json({ detail: `run not found: ${context.params.runId}` }, { status: 404 });
  }
  return NextResponse.json(item);
}
