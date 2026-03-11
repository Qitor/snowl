import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

import { NextResponse } from "next/server";

import { getMonitorStore } from "@/server/monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function readJsonObject(filePath: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // ignore malformed files
  }
  return {};
}

export async function POST(_request: Request, context: { params: { runId: string } }) {
  const store = getMonitorStore();
  const snapshot = store.runSnapshot(context.params.runId);
  if (!snapshot) {
    return NextResponse.json({ detail: `run not found: ${context.params.runId}` }, { status: 404 });
  }

  const status = String(snapshot.status || "").trim().toLowerCase();
  const runnerAlive = Boolean(snapshot.runner_alive);
  if (status === "running" && runnerAlive) {
    return NextResponse.json(
      { detail: `run ${context.params.runId} is still active; stop it before retrying` },
      { status: 409 },
    );
  }

  const runDir = String(snapshot.path || "").trim();
  if (!runDir) {
    return NextResponse.json({ detail: `run path unavailable for ${context.params.runId}` }, { status: 500 });
  }

  const manifest = readJsonObject(path.join(runDir, "manifest.json"));
  const source = ((manifest.source as Record<string, unknown>) || {}) as Record<string, unknown>;
  const projectPath =
    String(source.project_path || source.project_root || process.env.SNOWL_PROJECT_DIR || "").trim() ||
    path.dirname(runDir);

  const child = spawn(
    "snowl",
    [
      "retry",
      context.params.runId,
      "--project",
      projectPath,
      "--no-ui",
      "--no-web-monitor",
    ],
    {
      detached: true,
      stdio: "ignore",
      env: {
        ...process.env,
        SNOWL_AUTO_WEB_BOOTSTRAP: "0",
      },
    },
  );
  child.unref();

  return NextResponse.json({
    ok: true,
    run_id: context.params.runId,
    project_path: projectPath,
    pid: child.pid,
    command: `snowl retry ${context.params.runId}`,
  });
}
