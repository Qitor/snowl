import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const store = getMonitorStore();
  return NextResponse.json({
    ok: true,
    project_dir: store.projectDir,
    monitor_runtime: "next",
    cache_key: process.env.SNOWL_WEB_CACHE_KEY || null,
    source_dir: process.env.SNOWL_WEB_SOURCE_DIR || null,
    source_mode: process.env.SNOWL_WEB_SOURCE_MODE || null,
    pid: process.pid,
    cwd: process.cwd(),
    env_project_dir: process.env.SNOWL_PROJECT_DIR || null,
  });
}
