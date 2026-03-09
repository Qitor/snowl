import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";

export async function GET(request: Request, context: { params: { runId: string } }) {
  const url = new URL(request.url);
  const trialKey = (url.searchParams.get("trial_key") || "").trim();
  if (!trialKey) {
    return NextResponse.json({ detail: "trial_key is required" }, { status: 400 });
  }
  const store = getMonitorStore();
  const items = store.getPretaskEvents({ runId: context.params.runId, trialKey });
  return NextResponse.json({ run_id: context.params.runId, trial_key: trialKey, items });
}
