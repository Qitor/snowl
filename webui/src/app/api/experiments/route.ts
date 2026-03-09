import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";

export async function GET() {
  const store = getMonitorStore();
  return NextResponse.json({ items: store.listExperiments() });
}
