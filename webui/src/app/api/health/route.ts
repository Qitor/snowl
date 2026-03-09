import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";

export async function GET() {
  const store = getMonitorStore();
  return NextResponse.json({ ok: true, project_dir: store.projectDir });
}
