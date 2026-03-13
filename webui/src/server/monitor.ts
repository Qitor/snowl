import { EventEmitter } from "node:events";
import fs from "node:fs";
import path from "node:path";

import Database from "better-sqlite3";

type JsonRecord = Record<string, unknown>;

type RunState = {
  runId: string;
  runDir: string;
  runLogPath: string;
  eventsPath: string;
  manifestPath: string;
  runtimeStatePath: string;
  summaryPath: string;
  planPath: string;
  aggregatePath: string;
  profilingPath: string;
  recoveryPath: string;
  eventPos: number;
  eventTail: string;
  lastEventIndex: number;
  updatedAtMs: number;
  status: "running" | "completed" | "cancelled" | "zombie";
  statusReason: string;
  runnerAlive: boolean;
  observerStale: boolean;
  experimentId: string;
  benchmark: string;
  summary: JsonRecord;
  plan: JsonRecord;
  profiling: JsonRecord;
  runtimeState: JsonRecord;
};

type MonitorOptions = {
  projectDir?: string;
  pollIntervalSec?: number;
  maxEventBuffer?: number;
};

type RuntimeConfig = {
  project_dir?: string;
  poll_interval_sec?: number;
};

type TrialKeyParts = {
  taskId: string;
  agentId: string;
  variantId: string;
  sampleId: string;
};

type IdentityRow = {
  taskId: string;
  agentId: string;
  variantId: string;
  model: string | null;
  displayId: string;
  count: number;
  statusCounts: Record<string, number>;
  metrics: Record<string, number>;
};

type TaskMonitorRow = {
  taskId: string;
  agentId: string;
  variantId: string;
  sampleId: string | null;
  model: string | null;
  status: string;
  stepCount: number;
  startedAtMs: number | null;
  endedAtMs: number | null;
  durationMs: number | null;
  latestAction: string | null;
  latestObservation: string | null;
  latestMessage: string | null;
  scorerMetrics: Record<string, number>;
};

type LiveSummaryIdentity = {
  display_id: string;
  agent_id: string;
  variant_id: string;
  model: string | null;
  metrics: Record<string, number>;
  rank_score: number;
  count: number;
  status_counts: Record<string, number>;
  scored_trials: number;
  metric_counts: Record<string, number>;
};

type RunLiveSignals = {
  stalled: boolean;
  attentionCount: number;
  hasTaskMonitor: boolean;
  heartbeatOnly: boolean;
  lastProgressTsMs: number | null;
  attentionTaskCount: number;
  lastMetricTsMs: number | null;
};

type RecoveryCounters = {
  recoverableTrials: number;
  retriedTrials: number;
  recoveredTrials: number;
  stillFailingTrials: number;
  unfinishedTrials: number;
};

const STALLED_PROGRESS_MS = 30_000;
const LONG_RUNNING_TASK_MS = 45_000;
const ABANDONED_RUN_MS = 120_000;
const RUNNER_HEARTBEAT_STALE_MS = 15_000;
const OBSERVER_STALE_MS = 20_000;

function nowMs(): number {
  return Date.now();
}

function parseJsonObject(raw: string): JsonRecord {
  try {
    const data = JSON.parse(raw);
    if (data && typeof data === "object" && !Array.isArray(data)) {
      return data as JsonRecord;
    }
  } catch {
    // no-op
  }
  return {};
}

function readJsonObject(filePath: string): JsonRecord {
  try {
    return parseJsonObject(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return {};
  }
}

function fileMtimeMs(filePath: string): number {
  try {
    return fs.statSync(filePath).mtimeMs;
  } catch {
    return 0;
  }
}

function processAlive(pid: number): boolean {
  if (!Number.isFinite(pid) || pid <= 0) {
    return false;
  }
  try {
    process.kill(Math.trunc(pid), 0);
    return true;
  } catch {
    return false;
  }
}

function asInt(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string" && value.trim()) {
    const n = Number(value);
    if (Number.isFinite(n)) {
      return Math.trunc(n);
    }
  }
  return fallback;
}

function parseEventId(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const text = value.includes(":") ? value.split(":").at(-1) ?? "" : value;
  const parsed = Number(text);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return 0;
  }
  return Math.trunc(parsed);
}

function normalizeDimension(value: string | null | undefined): "variant-first" | "benchmark-first" {
  return value === "benchmark-first" ? "benchmark-first" : "variant-first";
}

function readRuntimeConfig(): RuntimeConfig {
  const cfgPath = path.join(process.cwd(), ".snowl-monitor.json");
  try {
    const raw = fs.readFileSync(cfgPath, "utf-8");
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    const row = parsed as Record<string, unknown>;
    return {
      project_dir: typeof row.project_dir === "string" ? row.project_dir : undefined,
      poll_interval_sec: Number.isFinite(Number(row.poll_interval_sec)) ? Number(row.poll_interval_sec) : undefined,
    };
  } catch {
    return {};
  }
}

function parseTrialKey(trialKey: string): TrialKeyParts | null {
  const parts = String(trialKey || "").split("::");
  if (parts.length < 4) {
    return null;
  }
  return {
    taskId: parts[0] || "",
    agentId: parts[1] || "",
    variantId: parts[2] || "default",
    sampleId: parts.slice(3).join("::"),
  };
}

function makeDisplayId(input: { agentId?: string | null; variantId?: string | null; model?: string | null }): string {
  const agentId = String(input.agentId || "unknown").trim() || "unknown";
  const variantId = String(input.variantId || "default").trim() || "default";
  const model = String(input.model || "").trim();
  if (variantId !== "default") {
    return `${agentId} / ${variantId}`;
  }
  if (model) {
    return `${agentId} / ${model}`;
  }
  return agentId;
}

function makeIdentityKey(input: { agentId?: string | null; variantId?: string | null; model?: string | null }): string {
  return `${String(input.agentId || "")}::${String(input.variantId || "default")}::${String(input.model || "")}`;
}

function parsePayload(event: JsonRecord): JsonRecord {
  const payload = event.payload;
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    return payload as JsonRecord;
  }
  return {};
}

function taskRowKey(input: { taskId?: string | null; agentId?: string | null; variantId?: string | null; sampleId?: string | null }): string {
  return `${String(input.taskId || "")}::${String(input.agentId || "")}::${String(input.variantId || "default")}::${String(input.sampleId || "-")}`;
}

export class RunMonitorStore {
  readonly projectDir: string;
  readonly runsRoot: string;
  readonly byRunIdDir: string;
  readonly dbPath: string;
  private readonly db: Database.Database;
  private readonly emitter = new EventEmitter();
  private readonly runs = new Map<string, RunState>();
  private readonly maxEventBuffer: number;
  private timer: NodeJS.Timeout | null = null;
  private readonly pollIntervalMs: number;

  constructor(opts: MonitorOptions = {}) {
    this.projectDir = path.resolve(opts.projectDir || process.env.SNOWL_PROJECT_DIR || process.cwd());
    this.runsRoot = path.join(this.projectDir, ".snowl", "runs");
    this.byRunIdDir = path.join(this.runsRoot, "by_run_id");
    this.maxEventBuffer = Math.max(256, Number(opts.maxEventBuffer || 4000));
    this.pollIntervalMs = Math.max(100, Math.floor((opts.pollIntervalSec || Number(process.env.SNOWL_POLL_INTERVAL_SEC) || 0.5) * 1000));

    fs.mkdirSync(this.runsRoot, { recursive: true });
    fs.mkdirSync(this.byRunIdDir, { recursive: true });

    this.dbPath = path.join(this.runsRoot, "web_monitor.sqlite");
    this.db = new Database(this.dbPath);
    this.db.pragma("journal_mode = WAL");
    this.ensureTables();
  }

  start(): void {
    if (this.timer) {
      return;
    }
    this.pollOnce();
    this.timer = setInterval(() => {
      try {
        this.pollOnce();
      } catch {
        // ignore polling errors to keep monitor alive
      }
    }, this.pollIntervalMs);
    this.timer.unref?.();
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.db.close();
  }

  private ensureTables(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        experiment_id TEXT,
        benchmark TEXT,
        run_dir TEXT,
        status TEXT,
        updated_at_ms INTEGER,
        summary_json TEXT,
        plan_json TEXT,
        manifest_json TEXT
      );

      CREATE TABLE IF NOT EXISTS events (
        run_id TEXT NOT NULL,
        event_index INTEGER NOT NULL,
        event_id TEXT NOT NULL,
        ts_ms INTEGER,
        event_name TEXT,
        trial_key TEXT,
        benchmark TEXT,
        agent_id TEXT,
        variant_id TEXT,
        task_id TEXT,
        sample_id TEXT,
        event_json TEXT NOT NULL,
        PRIMARY KEY (run_id, event_index)
      );

      CREATE INDEX IF NOT EXISTS idx_events_run_event_id ON events(run_id, event_id);
      CREATE INDEX IF NOT EXISTS idx_events_run_trial ON events(run_id, trial_key);
    `);
  }

  private resolveRunDir(pointerPath: string): string | null {
    try {
      const stat = fs.lstatSync(pointerPath);
      if (stat.isSymbolicLink()) {
        const target = fs.realpathSync(pointerPath);
        return fs.existsSync(target) ? target : null;
      }
      if (stat.isDirectory()) {
        return pointerPath;
      }
    } catch {
      return null;
    }

    try {
      const raw = fs.readFileSync(pointerPath, "utf-8").trim();
      if (!raw) {
        return null;
      }
      const target = path.isAbsolute(raw) ? raw : path.resolve(path.dirname(pointerPath), raw);
      return fs.existsSync(target) ? target : null;
    } catch {
      return null;
    }
  }

  private iterRunPointers(): Array<{ runId: string; runDir: string }> {
    const out: Array<{ runId: string; runDir: string }> = [];
    if (fs.existsSync(this.byRunIdDir)) {
      for (const entry of fs.readdirSync(this.byRunIdDir).sort()) {
        const pointer = path.join(this.byRunIdDir, entry);
        const runDir = this.resolveRunDir(pointer);
        if (runDir) {
          out.push({ runId: entry, runDir });
        }
      }
    }
    if (out.length > 0) {
      return out;
    }
    if (!fs.existsSync(this.runsRoot)) {
      return out;
    }
    for (const entry of fs.readdirSync(this.runsRoot).sort()) {
      const runDir = path.join(this.runsRoot, entry);
      if (!fs.existsSync(runDir) || !fs.statSync(runDir).isDirectory() || entry === "by_run_id") {
        continue;
      }
      out.push({ runId: `run-${entry}`, runDir });
    }
    return out;
  }

  private inferExperimentId(runId: string, manifest: JsonRecord, profiling: JsonRecord): string {
    const fromManifest = String(manifest.experiment_id || "").trim();
    if (fromManifest) {
      return fromManifest;
    }
    const runMeta = (profiling.run as JsonRecord) || {};
    const fromProfiling = String(runMeta.experiment_id || "").trim();
    if (fromProfiling) {
      return fromProfiling;
    }
    return runId;
  }

  private inferBenchmark(state: RunState, manifest: JsonRecord, profiling: JsonRecord): string {
    const runMeta = (profiling.run as JsonRecord) || {};
    const fromRun = String(runMeta.benchmark || "").trim().toLowerCase();
    if (fromRun) {
      return fromRun;
    }
    const fromManifest = String(manifest.benchmark || "").trim().toLowerCase();
    if (fromManifest) {
      return fromManifest;
    }
    const row = this.db
      .prepare("SELECT benchmark FROM events WHERE run_id = ? AND benchmark != '' ORDER BY event_index ASC LIMIT 1")
      .get(state.runId) as { benchmark?: string } | undefined;
    return String(row?.benchmark || "").trim().toLowerCase() || "custom";
  }

  private inferRunStatus(
    state: RunState,
    manifest: JsonRecord,
    runtimeState: JsonRecord,
  ): {
    status: "running" | "completed" | "cancelled" | "zombie";
    statusReason: string;
    runnerAlive: boolean;
    observerStale: boolean;
  } {
    const manifestStatus = String(manifest.status || manifest.run_status || "").trim().toLowerCase();
    const runtimeStatus = String(runtimeState.status || "").trim().toLowerCase();
    if (runtimeStatus === "running") {
      const latestEventRow = this.db
        .prepare("SELECT ts_ms FROM events WHERE run_id = ? ORDER BY event_index DESC LIMIT 1")
        .get(state.runId) as { ts_ms?: number } | undefined;
      const latestEventTs = asInt(latestEventRow?.ts_ms, 0);
      const updatedAtMs = this.computeRunUpdatedAt(state);
      const heartbeatTs = asInt(runtimeState.heartbeat_ts_ms, 0);
      const lastRuntimeEventTs = asInt(runtimeState.last_event_ts_ms, 0);
      const ownerPid = asInt(runtimeState.owner_pid, 0);
      const pidAlive = processAlive(ownerPid);
      const heartbeatFresh = heartbeatTs > 0 && nowMs() - heartbeatTs < RUNNER_HEARTBEAT_STALE_MS;
      const runnerAlive = pidAlive || heartbeatFresh;
      const observerSignalTs = Math.max(latestEventTs, lastRuntimeEventTs, fileMtimeMs(state.eventsPath), fileMtimeMs(state.profilingPath), 0);
      const observerStale =
        runnerAlive &&
        heartbeatTs > 0 &&
        observerSignalTs > 0 &&
        heartbeatTs - observerSignalTs >= OBSERVER_STALE_MS;

      if (runnerAlive) {
        return {
          status: "running",
          statusReason: observerStale ? "runner_alive_observer_stale" : (pidAlive ? "runner_pid_alive" : "runner_heartbeat_fresh"),
          runnerAlive,
          observerStale,
        };
      }
      return {
        status: "zombie",
        statusReason: "runtime_running_but_runner_dead",
        runnerAlive: false,
        observerStale: false,
      };
    }

    if (runtimeStatus === "completed" || manifestStatus === "completed") {
      return {
        status: "completed",
        statusReason: runtimeStatus === "completed" ? "runtime_completed" : "manifest_completed",
        runnerAlive: false,
        observerStale: false,
      };
    }
    if (runtimeStatus === "cancelled" || runtimeStatus === "canceled" || manifestStatus === "cancelled" || manifestStatus === "canceled") {
      return {
        status: "cancelled",
        statusReason: runtimeStatus.startsWith("cancel") ? "runtime_cancelled" : "manifest_cancelled",
        runnerAlive: false,
        observerStale: false,
      };
    }

    if (Object.keys(state.summary).length > 0) {
      return {
        status: "completed",
        statusReason: "summary_present",
        runnerAlive: false,
        observerStale: false,
      };
    }

    const latestEventRow = this.db
      .prepare("SELECT ts_ms FROM events WHERE run_id = ? ORDER BY event_index DESC LIMIT 1")
      .get(state.runId) as { ts_ms?: number } | undefined;
    const latestEventTs = asInt(latestEventRow?.ts_ms, 0);
    const updatedAtMs = this.computeRunUpdatedAt(state);
    const heartbeatTs = asInt(runtimeState.heartbeat_ts_ms, 0);
    const lastRuntimeEventTs = asInt(runtimeState.last_event_ts_ms, 0);
    const ownerPid = asInt(runtimeState.owner_pid, 0);
    const pidAlive = processAlive(ownerPid);
    const heartbeatFresh = heartbeatTs > 0 && nowMs() - heartbeatTs < RUNNER_HEARTBEAT_STALE_MS;
    const runnerAlive = pidAlive || heartbeatFresh;
    const freshestSignalTs = Math.max(latestEventTs, lastRuntimeEventTs, heartbeatTs, updatedAtMs, 0);
    const observerSignalTs = Math.max(latestEventTs, lastRuntimeEventTs, fileMtimeMs(state.eventsPath), fileMtimeMs(state.profilingPath), 0);
    const observerStale =
      runnerAlive &&
      heartbeatTs > 0 &&
      observerSignalTs > 0 &&
      heartbeatTs - observerSignalTs >= OBSERVER_STALE_MS;

    if (freshestSignalTs > 0 && nowMs() - freshestSignalTs >= ABANDONED_RUN_MS) {
      return {
        status: "zombie",
        statusReason: runtimeState.run_id ? "stale_runtime_state" : "stale_without_terminal_summary",
        runnerAlive: false,
        observerStale: false,
      };
    }

    return {
      status: "running",
      statusReason: "recent_signal",
      runnerAlive,
      observerStale,
    };
  }

  private upsertRunRow(state: RunState, manifest: JsonRecord): void {
    const stmt = this.db.prepare(`
      INSERT INTO runs(run_id, experiment_id, benchmark, run_dir, status, updated_at_ms, summary_json, plan_json, manifest_json)
      VALUES(@run_id, @experiment_id, @benchmark, @run_dir, @status, @updated_at_ms, @summary_json, @plan_json, @manifest_json)
      ON CONFLICT(run_id) DO UPDATE SET
        experiment_id=excluded.experiment_id,
        benchmark=excluded.benchmark,
        run_dir=excluded.run_dir,
        status=excluded.status,
        updated_at_ms=excluded.updated_at_ms,
        summary_json=excluded.summary_json,
        plan_json=excluded.plan_json,
        manifest_json=excluded.manifest_json
    `);
    stmt.run({
      run_id: state.runId,
      experiment_id: state.experimentId,
      benchmark: state.benchmark,
      run_dir: state.runDir,
      status: state.status,
      updated_at_ms: state.updatedAtMs,
      summary_json: JSON.stringify(state.summary),
      plan_json: JSON.stringify(state.plan),
      manifest_json: JSON.stringify(manifest),
    });
  }

  private refreshRunMetadata(state: RunState): void {
    const manifest = readJsonObject(state.manifestPath);
    state.runtimeState = readJsonObject(state.runtimeStatePath);
    state.summary = readJsonObject(state.summaryPath);
    state.plan = readJsonObject(state.planPath);
    state.profiling = readJsonObject(state.profilingPath);
    state.experimentId = this.inferExperimentId(state.runId, manifest, state.profiling);
    state.benchmark = this.inferBenchmark(state, manifest, state.profiling);
    state.updatedAtMs = this.computeRunUpdatedAt(state);
    const inferred = this.inferRunStatus(state, manifest, state.runtimeState);
    state.status = inferred.status;
    state.statusReason = inferred.statusReason;
    state.runnerAlive = inferred.runnerAlive;
    state.observerStale = inferred.observerStale;
    this.upsertRunRow(state, manifest);
  }

  private computeRunUpdatedAt(state: RunState): number {
    const candidates = [
      fileMtimeMs(state.runDir),
      fileMtimeMs(state.eventsPath),
      fileMtimeMs(state.manifestPath),
      fileMtimeMs(state.runtimeStatePath),
      fileMtimeMs(state.summaryPath),
      fileMtimeMs(state.planPath),
      fileMtimeMs(state.aggregatePath),
      fileMtimeMs(state.profilingPath),
    ];
    const computed = Math.max(...candidates, 0);
    return computed > 0 ? computed : state.updatedAtMs || 0;
  }

  private emitEvent(runId: string, event: JsonRecord): void {
    this.emitter.emit(`run:${runId}`, event);
  }

  private ingestEvents(state: RunState): number {
    if (!fs.existsSync(state.eventsPath)) {
      return 0;
    }

    let fileSize = 0;
    try {
      fileSize = fs.statSync(state.eventsPath).size;
    } catch {
      return 0;
    }

    if (fileSize < state.eventPos) {
      state.eventPos = 0;
      state.eventTail = "";
      state.lastEventIndex = 0;
    }

    const bytesToRead = fileSize - state.eventPos;
    if (bytesToRead <= 0) {
      return 0;
    }

    const fd = fs.openSync(state.eventsPath, "r");
    const chunk = Buffer.allocUnsafe(bytesToRead);
    fs.readSync(fd, chunk, 0, bytesToRead, state.eventPos);
    fs.closeSync(fd);

    state.eventPos = fileSize;
    const text = state.eventTail + chunk.toString("utf-8");
    const lines = text.split(/\r?\n/);
    state.eventTail = lines.pop() || "";

    const insertEventStmt = this.db.prepare(`
      INSERT OR IGNORE INTO events(
        run_id, event_index, event_id, ts_ms, event_name, trial_key, benchmark,
        agent_id, variant_id, task_id, sample_id, event_json
      ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    let ingested = 0;
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) {
        continue;
      }
      let event: JsonRecord;
      try {
        const parsed = JSON.parse(line);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          continue;
        }
        event = parsed as JsonRecord;
      } catch {
        continue;
      }
      const eventIndex = asInt(event.event_index, state.lastEventIndex + 1);
      const eventId = String(event.event_id || `${state.runId}:${eventIndex}`);
      state.lastEventIndex = Math.max(state.lastEventIndex, eventIndex);
      event.event_index = eventIndex;
      event.seq = asInt(event.seq, eventIndex);
      event.event_id = eventId;
      event.run_id = state.runId;

      const info = insertEventStmt.run(
        state.runId,
        eventIndex,
        eventId,
        asInt(event.ts_ms, 0),
        String(event.event || ""),
        String(event.trial_key || ""),
        String(event.benchmark || ""),
        String(event.agent_id || ""),
        String(event.variant_id || ""),
        String(event.task_id || ""),
        String(event.sample_id || ""),
        JSON.stringify(event),
      );
      if ((info.changes || 0) > 0) {
        ingested += 1;
        this.emitEvent(state.runId, event);
      }
    }

    if (ingested > 0) {
      state.updatedAtMs = this.computeRunUpdatedAt(state);
    }
    return ingested;
  }

  pollOnce(): { runs: number; discovered: number; ingested: number } {
    const pointers = this.iterRunPointers();
    let discovered = 0;
    let ingested = 0;

    for (const pointer of pointers) {
      const existing = this.runs.get(pointer.runId);
      if (!existing) {
        this.runs.set(pointer.runId, {
          runId: pointer.runId,
          runDir: pointer.runDir,
          runLogPath: path.join(pointer.runDir, "run.log"),
          eventsPath: path.join(pointer.runDir, "events.jsonl"),
          manifestPath: path.join(pointer.runDir, "manifest.json"),
          runtimeStatePath: path.join(pointer.runDir, "runtime_state.json"),
          summaryPath: path.join(pointer.runDir, "summary.json"),
          planPath: path.join(pointer.runDir, "plan.json"),
          aggregatePath: path.join(pointer.runDir, "aggregate.json"),
          profilingPath: path.join(pointer.runDir, "profiling.json"),
          recoveryPath: path.join(pointer.runDir, "recovery.json"),
          eventPos: 0,
          eventTail: "",
          lastEventIndex: 0,
          updatedAtMs: nowMs(),
          status: "running",
          statusReason: "discovered",
          runnerAlive: false,
          observerStale: false,
          experimentId: pointer.runId,
          benchmark: "custom",
          summary: {},
          plan: {},
          profiling: {},
          runtimeState: {},
        });
        discovered += 1;
      } else if (existing.runDir !== pointer.runDir) {
        existing.runDir = pointer.runDir;
        existing.runLogPath = path.join(pointer.runDir, "run.log");
        existing.eventsPath = path.join(pointer.runDir, "events.jsonl");
        existing.manifestPath = path.join(pointer.runDir, "manifest.json");
        existing.runtimeStatePath = path.join(pointer.runDir, "runtime_state.json");
        existing.summaryPath = path.join(pointer.runDir, "summary.json");
        existing.planPath = path.join(pointer.runDir, "plan.json");
        existing.aggregatePath = path.join(pointer.runDir, "aggregate.json");
        existing.profilingPath = path.join(pointer.runDir, "profiling.json");
        existing.recoveryPath = path.join(pointer.runDir, "recovery.json");
      }

      const state = this.runs.get(pointer.runId);
      if (!state) {
        continue;
      }
      this.refreshRunMetadata(state);
      ingested += this.ingestEvents(state);
    }

    return { runs: this.runs.size, discovered, ingested };
  }

  private computeProgress(state: RunState): { done: number; total: number; failed: number } {
    const logProgress = this.readRunLogProgress(state);
    const effectiveRows = this.effectiveRecoveryRows(state);
    if (effectiveRows.length > 0) {
      const total = asInt(state.plan.trial_count, 0) || logProgress.total;
      const done = effectiveRows.length;
      const failed = effectiveRows.filter((row) => {
        const taskResult = ((row.task_result as JsonRecord) || {}) as JsonRecord;
        const status = String(taskResult.status || row.status || "").trim().toLowerCase();
        return status !== "success";
      }).length;
      return { done, total, failed };
    }
    if (state.summary && Object.keys(state.summary).length > 0) {
      const summaryTotal = asInt(state.summary.total, 0);
      const planTotal = asInt(state.plan.trial_count, 0);
      const total = summaryTotal > 0 ? summaryTotal : planTotal > 0 ? planTotal : logProgress.total;
      const failed = asInt(state.summary.error, 0) + asInt(state.summary.limit_exceeded, 0) + asInt(state.summary.cancelled, 0);
      if (summaryTotal > 0 && state.status === "completed") {
        return { done: summaryTotal, total, failed };
      }
      const doneRow = this.db
        .prepare("SELECT COUNT(*) AS c FROM events WHERE run_id = ? AND event_name='runtime.trial.finish'")
        .get(state.runId) as { c?: number };
      const done = asInt(doneRow?.c, 0) || logProgress.done;
      return { done, total, failed };
    }
    const total = asInt(state.plan.trial_count, 0) || logProgress.total;
    const doneRow = this.db
      .prepare("SELECT COUNT(*) AS c FROM events WHERE run_id = ? AND event_name='runtime.trial.finish'")
      .get(state.runId) as { c?: number };
    const failRow = this.db
      .prepare("SELECT COUNT(*) AS c FROM events WHERE run_id = ? AND event_name='runtime.trial.error'")
      .get(state.runId) as { c?: number };
    return { done: asInt(doneRow?.c, 0) || logProgress.done, total, failed: asInt(failRow?.c, 0) };
  }

  private readRunLogProgress(state: RunState): { done: number; total: number } {
    try {
      const raw = fs.readFileSync(state.runLogPath, "utf-8");
      const patterns = [/progress=(\d+)\/(\d+)/g, /\[(\d+)\/(\d+)\]\s+task=/g, /idx=(\d+)\/(\d+)/g];
      let done = 0;
      let total = 0;
      for (const pattern of patterns) {
        for (const match of raw.matchAll(pattern)) {
          done = asInt(match[1], done);
          total = asInt(match[2], total);
        }
      }
      return { done, total };
    } catch {
      return { done: 0, total: 0 };
    }
  }

  private computeRunLiveSignals(state: RunState, taskRows?: TaskMonitorRow[]): RunLiveSignals {
    const rows = taskRows || this.collectTaskMonitorRows(state);
    const latestEventRow = this.db
      .prepare("SELECT ts_ms, event_name, event_json FROM events WHERE run_id = ? ORDER BY event_index DESC LIMIT 1")
      .get(state.runId) as { ts_ms?: number; event_name?: string; event_json?: string } | undefined;
    const lastProgressRow = this.db
      .prepare(
        `
          SELECT ts_ms, event_json FROM events
          WHERE run_id = ?
            AND event_name IN (
              'runtime.trial.start',
              'runtime.trial.finish',
              'runtime.trial.error',
              'runtime.scorer.start',
              'runtime.scorer.finish',
              'runtime.model.query.start',
              'runtime.model.query.finish',
              'runtime.agent.step'
            )
          ORDER BY event_index DESC
          LIMIT 1
        `,
      )
      .get(state.runId) as { ts_ms?: number; event_json?: string } | undefined;
    const lastMetricRow = this.db
      .prepare(
        `
          SELECT ts_ms FROM events
          WHERE run_id = ? AND event_name = 'runtime.scorer.finish'
          ORDER BY event_index DESC
          LIMIT 1
        `,
      )
      .get(state.runId) as { ts_ms?: number } | undefined;
    const attentionEventRow = this.db
      .prepare(
        `
          SELECT 1 AS c FROM events
          WHERE run_id = ?
            AND (
              event_name LIKE '%error%'
              OR event_name LIKE '%failed%'
              OR event_name = 'pretask.failed'
            )
          LIMIT 1
        `,
      )
      .get(state.runId) as { c?: number } | undefined;
    const latestTs = asInt(latestEventRow?.ts_ms, 0);
    const lastProgressTs = asInt(lastProgressRow?.ts_ms, 0) || null;
    const latestEventName = String(latestEventRow?.event_name || "").toLowerCase();
    const now = nowMs();
    const heartbeatOnly = Boolean(
      !state.observerStale && latestEventName === "ui.heartbeat" && lastProgressTs === null && latestTs > 0,
    );
    const stalled =
      state.status === "running" &&
      !state.observerStale &&
      ((lastProgressTs !== null && now - lastProgressTs >= STALLED_PROGRESS_MS) ||
        (lastProgressTs === null && latestTs > 0 && now - latestTs >= STALLED_PROGRESS_MS));
    const erroredTaskCount = rows.filter((row) => row.status === "error").length;
    const longRunningTaskCount = rows.filter((row) => {
      if (row.status === "running" || row.status === "scoring") {
        return row.startedAtMs != null && now - row.startedAtMs >= LONG_RUNNING_TASK_MS;
      }
      return false;
    }).length;
    const attentionTaskCount = erroredTaskCount + longRunningTaskCount;
    const missingTaskMonitor = state.status === "running" && asInt(state.plan.trial_count, 0) > 0 && rows.length === 0;
    const hasAttentionEvents = Boolean(asInt(attentionEventRow?.c, 0));
    const attentionCount =
      attentionTaskCount +
      (stalled ? 1 : 0) +
      (missingTaskMonitor ? 1 : 0) +
      (heartbeatOnly ? 1 : 0) +
      (hasAttentionEvents && attentionTaskCount === 0 ? 1 : 0);
    return {
      stalled,
      attentionCount,
      hasTaskMonitor: rows.length > 0,
      heartbeatOnly,
      lastProgressTsMs: lastProgressTs,
      attentionTaskCount,
      lastMetricTsMs: asInt(lastMetricRow?.ts_ms, 0) || null,
    };
  }

  private collectTaskMonitorRowsFromProfiling(state: RunState): TaskMonitorRow[] {
    const taskMonitor = Array.isArray(state.profiling.task_monitor) ? state.profiling.task_monitor : [];
    const rows: TaskMonitorRow[] = [];
    for (const raw of taskMonitor) {
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
        continue;
      }
      const row = raw as JsonRecord;
      rows.push({
        taskId: String(row.task_id || "-"),
        agentId: String(row.agent_id || "unknown"),
        variantId: String(row.variant_id || "default"),
        sampleId: row.sample_id == null ? null : String(row.sample_id),
        model: String(row.model || "").trim() || null,
        status: String(row.status || "queued").toLowerCase(),
        stepCount: asInt(row.step_count, 0),
        startedAtMs: row.started_at_ms == null ? null : asInt(row.started_at_ms, 0),
        endedAtMs: row.ended_at_ms == null ? null : asInt(row.ended_at_ms, 0),
        durationMs: row.duration_ms == null ? null : asInt(row.duration_ms, 0),
        latestAction: String(row.latest_action || "").trim() || null,
        latestObservation: String(row.latest_observation || "").trim() || null,
        latestMessage: String(row.latest_message || "").trim() || null,
        scorerMetrics:
          row.scorer_metrics && typeof row.scorer_metrics === "object" && !Array.isArray(row.scorer_metrics)
            ? Object.fromEntries(
                Object.entries(row.scorer_metrics as JsonRecord)
                  .map(([key, value]) => [key, Number(value)])
                  .filter((entry) => Number.isFinite(entry[1])),
              )
            : {},
      });
    }
    return rows;
  }

  private collectTaskMonitorRowsFromEvents(state: RunState): TaskMonitorRow[] {
    const rows = this.db
      .prepare(
        `
          SELECT event_json FROM events
          WHERE run_id = ? AND trial_key != ''
          ORDER BY event_index ASC
        `,
      )
      .all(state.runId) as Array<{ event_json: string }>;
    const grouped = new Map<string, TaskMonitorRow>();
    for (const row of rows) {
      const event = parseJsonObject(row.event_json);
      if (Object.keys(event).length === 0) {
        continue;
      }
      const payload = parsePayload(event);
      const trial = parseTrialKey(String(event.trial_key || "")) || null;
      const taskId = String(event.task_id || trial?.taskId || "-");
      const agentId = String(event.agent_id || trial?.agentId || "unknown");
      const variantId = String(event.variant_id || trial?.variantId || "default");
      const sampleId =
        event.sample_id != null
          ? String(event.sample_id)
          : payload.sample_id != null
            ? String(payload.sample_id)
            : (trial?.sampleId || null);
      const key = taskRowKey({ taskId, agentId, variantId, sampleId });
      if (!grouped.has(key)) {
        grouped.set(key, {
          taskId,
          agentId,
          variantId,
          sampleId,
          model: null,
          status: "queued",
          stepCount: 0,
          startedAtMs: null,
          endedAtMs: null,
          durationMs: null,
          latestAction: null,
          latestObservation: null,
          latestMessage: null,
          scorerMetrics: {},
        });
      }
      const slot = grouped.get(key) as TaskMonitorRow;
      const model = String(event.model || payload.model || "").trim();
      if (model) {
        slot.model = model;
      }
      const message = String(event.message || payload.message || "").trim();
      if (message) {
        slot.latestMessage = message;
      }
      const eventName = String(event.event || "");
      if (eventName === "runtime.trial.start") {
        slot.status = "running";
        slot.startedAtMs = asInt(event.ts_ms, slot.startedAtMs ?? 0) || slot.startedAtMs;
      } else if (eventName === "runtime.scorer.start") {
        slot.status = "scoring";
      } else if (eventName === "runtime.scorer.finish") {
        const metrics = payload.metrics || payload.scorer_metrics;
        if (metrics && typeof metrics === "object" && !Array.isArray(metrics)) {
          slot.scorerMetrics = Object.fromEntries(
            Object.entries(metrics as JsonRecord)
              .map(([keyName, value]) => [keyName, Number(value)])
              .filter((entry) => Number.isFinite(entry[1])),
          );
        }
      } else if (eventName === "runtime.trial.finish") {
        const rawStatus = String(payload.status || event.status || event.message || "success").trim().toLowerCase();
        slot.status = rawStatus || "success";
        slot.endedAtMs = asInt(event.ts_ms, slot.endedAtMs ?? 0) || slot.endedAtMs;
        if (slot.startedAtMs != null && slot.endedAtMs != null) {
          slot.durationMs = Math.max(0, slot.endedAtMs - slot.startedAtMs);
        }
      } else if (eventName === "runtime.trial.error") {
        slot.status = "error";
        slot.endedAtMs = asInt(event.ts_ms, slot.endedAtMs ?? 0) || slot.endedAtMs;
        if (slot.startedAtMs != null && slot.endedAtMs != null) {
          slot.durationMs = Math.max(0, slot.endedAtMs - slot.startedAtMs);
        }
      } else if (eventName.startsWith("runtime.trial.step") || eventName === "runtime.agent.step") {
        slot.stepCount += 1;
        const action = payload.action || payload.action_type;
        const observation = payload.observation || payload.observation_type;
        if (action != null) {
          slot.latestAction = String(action);
        }
        if (observation != null) {
          slot.latestObservation = String(observation);
        }
      }
    }
    return Array.from(grouped.values()).sort((a, b) => taskRowKey(a).localeCompare(taskRowKey(b)));
  }

  private collectTaskMonitorRows(state: RunState): TaskMonitorRow[] {
    const merged = new Map<string, TaskMonitorRow>();
    for (const row of this.collectTaskMonitorRowsFromProfiling(state)) {
      merged.set(taskRowKey(row), { ...row, scorerMetrics: { ...row.scorerMetrics } });
    }
    for (const row of this.collectTaskMonitorRowsFromEvents(state)) {
      const key = taskRowKey(row);
      const existing = merged.get(key);
      if (!existing) {
        merged.set(key, { ...row, scorerMetrics: { ...row.scorerMetrics } });
        continue;
      }
      merged.set(key, {
        ...existing,
        ...row,
        model: row.model || existing.model,
        latestAction: row.latestAction || existing.latestAction,
        latestObservation: row.latestObservation || existing.latestObservation,
        latestMessage: row.latestMessage || existing.latestMessage,
        scorerMetrics: Object.keys(row.scorerMetrics).length > 0 ? { ...row.scorerMetrics } : { ...existing.scorerMetrics },
      });
    }
    return Array.from(merged.values()).sort((a, b) => taskRowKey(a).localeCompare(taskRowKey(b)));
  }

  private collectIdentityRowsFromAggregate(state: RunState): IdentityRow[] {
    if (!fs.existsSync(state.aggregatePath)) {
      return [];
    }
    const aggregate = readJsonObject(state.aggregatePath);
    const byTaskAgent = (aggregate.by_task_agent as JsonRecord) || {};
    const rows: IdentityRow[] = [];
    for (const row of Object.values(byTaskAgent)) {
      if (!row || typeof row !== "object" || Array.isArray(row)) {
        continue;
      }
      const asRow = row as JsonRecord;
      const agentId = String(asRow.agent_id || "unknown");
      const variantId = String(asRow.variant_id || "default");
      const model = String(asRow.model || "").trim() || null;
      const metrics = ((asRow.metrics as JsonRecord) || {}) as JsonRecord;
      const statusCounts = ((asRow.status_counts as JsonRecord) || {}) as JsonRecord;
      rows.push({
        taskId: String(asRow.task_id || "-"),
        agentId,
        variantId,
        model,
        displayId: makeDisplayId({ agentId, variantId, model }),
        count: asInt(asRow.count, 0),
        statusCounts: Object.fromEntries(
          Object.entries(statusCounts).map(([key, value]) => [key, asInt(value, 0)]),
        ),
        metrics: Object.fromEntries(
          Object.entries(metrics)
            .map(([key, value]) => [key, Number(value)])
            .filter((entry) => Number.isFinite(entry[1])),
        ),
      });
    }
    return rows;
  }

  private collectIdentityRowsFromTaskMonitor(state: RunState): IdentityRow[] {
    const grouped = new Map<string, IdentityRow>();
    for (const asRow of this.collectTaskMonitorRows(state)) {
      const taskId = asRow.taskId;
      const agentId = asRow.agentId;
      const variantId = asRow.variantId;
      const model = asRow.model;
      const key = `${taskId}::${makeIdentityKey({ agentId, variantId, model })}`;
      if (!grouped.has(key)) {
        grouped.set(key, {
          taskId,
          agentId,
          variantId,
          model,
          displayId: makeDisplayId({ agentId, variantId, model }),
          count: 0,
          statusCounts: {},
          metrics: {},
        });
      }
      const slot = grouped.get(key) as IdentityRow;
      slot.count += 1;
      const status = String(asRow.status || "queued").toLowerCase();
      slot.statusCounts[status] = (slot.statusCounts[status] || 0) + 1;
      const metrics = asRow.scorerMetrics || {};
      for (const [metricName, metricValue] of Object.entries(metrics)) {
        const numeric = Number(metricValue);
        if (!Number.isFinite(numeric)) {
          continue;
        }
        slot.metrics[metricName] = numeric;
      }
    }
    return Array.from(grouped.values());
  }

  private collectIdentityRows(state: RunState): IdentityRow[] {
    const aggregateRows = this.collectIdentityRowsFromAggregate(state);
    if (aggregateRows.length > 0) {
      return aggregateRows;
    }
    return this.collectIdentityRowsFromTaskMonitor(state);
  }

  private collectRunIdentities(state: RunState): Array<{ display_id: string; agent_id: string; variant_id: string; model: string | null }> {
    const seen = new Map<string, { display_id: string; agent_id: string; variant_id: string; model: string | null }>();
    for (const row of this.collectIdentityRows(state)) {
      const key = makeIdentityKey({ agentId: row.agentId, variantId: row.variantId, model: row.model });
      if (!seen.has(key)) {
        seen.set(key, {
          display_id: row.displayId,
          agent_id: row.agentId,
          variant_id: row.variantId,
          model: row.model,
        });
      }
    }
    if (seen.size === 0) {
      const planAgentIds = Array.isArray(state.plan.agent_ids) ? state.plan.agent_ids : [];
      const planVariantIds = Array.isArray(state.plan.variant_ids) ? state.plan.variant_ids : [];
      for (const agentValue of planAgentIds) {
        for (const variantValue of planVariantIds.length > 0 ? planVariantIds : ["default"]) {
          const agentId = String(agentValue || "unknown");
          const variantId = String(variantValue || "default");
          const key = makeIdentityKey({ agentId, variantId, model: null });
          if (!seen.has(key)) {
            seen.set(key, {
              display_id: makeDisplayId({ agentId, variantId, model: null }),
              agent_id: agentId,
              variant_id: variantId,
              model: null,
            });
          }
        }
      }
    }
    return Array.from(seen.values()).sort((a, b) => a.display_id.localeCompare(b.display_id));
  }

  private buildLiveSummaryFromTaskRows(
    taskRows: TaskMonitorRow[],
    identities: Array<{ display_id: string; agent_id: string; variant_id: string; model: string | null }>,
    primaryDimension: "variant-first" | "benchmark-first",
  ): {
    agents: LiveSummaryIdentity[];
    matrix: Record<string, Record<string, number>>;
    scoredTrials: number;
    scoredTrialsByIdentity: Record<string, number>;
    metricCounts: Record<string, Record<string, number>>;
  } {
    const metadata = new Map<
      string,
      {
        display_id: string;
        agent_id: string;
        variant_id: string;
        model: string | null;
        count: number;
        status_counts: Record<string, number>;
      }
    >();
    for (const identity of identities) {
      const key = makeIdentityKey({ agentId: identity.agent_id, variantId: identity.variant_id, model: identity.model });
      metadata.set(key, {
        display_id: identity.display_id,
        agent_id: identity.agent_id,
        variant_id: identity.variant_id,
        model: identity.model,
        count: 0,
        status_counts: {},
      });
    }

    const metricSums = new Map<string, Map<string, number>>();
    const metricCounts = new Map<string, Map<string, number>>();
    const scoredTrialsByIdentity = new Map<string, number>();
    const matrixSums = new Map<string, Map<string, number>>();
    const matrixCounts = new Map<string, Map<string, number>>();
    let scoredTrials = 0;

    for (const row of taskRows) {
      const identityKey = makeIdentityKey({ agentId: row.agentId, variantId: row.variantId, model: row.model });
      if (!metadata.has(identityKey)) {
        metadata.set(identityKey, {
          display_id: makeDisplayId({ agentId: row.agentId, variantId: row.variantId, model: row.model }),
          agent_id: row.agentId,
          variant_id: row.variantId,
          model: row.model,
          count: 0,
          status_counts: {},
        });
      }
      const meta = metadata.get(identityKey) as {
        display_id: string;
        agent_id: string;
        variant_id: string;
        model: string | null;
        count: number;
        status_counts: Record<string, number>;
      };
      meta.count += 1;
      const status = String(row.status || "queued").toLowerCase();
      meta.status_counts[status] = (meta.status_counts[status] || 0) + 1;

      const metrics = row.scorerMetrics || {};
      let primaryMetric: number | null = null;
      let hasScoredMetric = false;
      for (const [metricName, metricValue] of Object.entries(metrics)) {
        const numeric = Number(metricValue);
        if (!Number.isFinite(numeric)) {
          continue;
        }
        hasScoredMetric = true;
        if (!metricSums.has(identityKey)) {
          metricSums.set(identityKey, new Map());
          metricCounts.set(identityKey, new Map());
        }
        const sums = metricSums.get(identityKey) as Map<string, number>;
        const counts = metricCounts.get(identityKey) as Map<string, number>;
        sums.set(metricName, (sums.get(metricName) || 0) + numeric);
        counts.set(metricName, (counts.get(metricName) || 0) + 1);
        if (primaryMetric === null) {
          primaryMetric = numeric;
        }
      }

      if (hasScoredMetric) {
        scoredTrials += 1;
        scoredTrialsByIdentity.set(meta.display_id, (scoredTrialsByIdentity.get(meta.display_id) || 0) + 1);
      }
      if (primaryMetric !== null) {
        const rowKey = primaryDimension === "benchmark-first" ? row.taskId : meta.display_id;
        const colKey = primaryDimension === "benchmark-first" ? meta.display_id : row.taskId;
        if (!matrixSums.has(rowKey)) {
          matrixSums.set(rowKey, new Map());
          matrixCounts.set(rowKey, new Map());
        }
        const sums = matrixSums.get(rowKey) as Map<string, number>;
        const counts = matrixCounts.get(rowKey) as Map<string, number>;
        sums.set(colKey, (sums.get(colKey) || 0) + primaryMetric);
        counts.set(colKey, (counts.get(colKey) || 0) + 1);
      }
    }

    const agents: LiveSummaryIdentity[] = Array.from(metadata.entries()).map(([identityKey, meta]) => {
      const sums = metricSums.get(identityKey) || new Map<string, number>();
      const counts = metricCounts.get(identityKey) || new Map<string, number>();
      const metrics: Record<string, number> = {};
      const metricCountRow: Record<string, number> = {};
      for (const [metricName, total] of sums.entries()) {
        const count = Math.max(1, counts.get(metricName) || 1);
        metrics[metricName] = total / count;
        metricCountRow[metricName] = count;
      }
      const rankScore = Object.values(metrics).length > 0 ? Math.max(...Object.values(metrics)) : 0;
      return {
        display_id: meta.display_id,
        agent_id: meta.agent_id,
        variant_id: meta.variant_id,
        model: meta.model,
        metrics,
        rank_score: rankScore,
        count: meta.count,
        status_counts: meta.status_counts,
        scored_trials: scoredTrialsByIdentity.get(meta.display_id) || 0,
        metric_counts: metricCountRow,
      };
    });
    agents.sort((a, b) => b.rank_score - a.rank_score || a.display_id.localeCompare(b.display_id));

    const matrix: Record<string, Record<string, number>> = {};
    for (const [rowKey, sums] of matrixSums.entries()) {
      matrix[rowKey] = {};
      const counts = matrixCounts.get(rowKey) || new Map<string, number>();
      for (const [colKey, total] of sums.entries()) {
        const count = Math.max(1, counts.get(colKey) || 1);
        matrix[rowKey][colKey] = total / count;
      }
    }

    return {
      agents,
      matrix,
      scoredTrials,
      scoredTrialsByIdentity: Object.fromEntries(scoredTrialsByIdentity.entries()),
      metricCounts: Object.fromEntries(agents.map((agent) => [agent.display_id, agent.metric_counts])),
    };
  }

  private buildRunSummary(state: RunState, primaryDimension: "variant-first" | "benchmark-first"): JsonRecord {
    const progress = this.computeProgress(state);
    const identities = this.collectRunIdentities(state);
    const taskRows = this.collectTaskMonitorRows(state);
    const liveSummary = this.buildLiveSummaryFromTaskRows(taskRows, identities, primaryDimension);
    const recoveryCounters = this.computeRecoveryCounters(state);
    let agents: Array<Record<string, unknown>>;
    let matrix: Record<string, Record<string, number>>;

    if (state.status === "running" || !fs.existsSync(state.aggregatePath)) {
      agents = liveSummary.agents;
      matrix = liveSummary.matrix;
    } else {
      const identityRows = this.collectIdentityRowsFromAggregate(state);
      const metricSums = new Map<string, Map<string, number>>();
      const metricCounts = new Map<string, Map<string, number>>();
      const metadata = new Map<string, { display_id: string; agent_id: string; variant_id: string; model: string | null; count: number; status_counts: Record<string, number> }>();
      matrix = {};

      for (const row of identityRows) {
        const key = makeIdentityKey({ agentId: row.agentId, variantId: row.variantId, model: row.model });
        if (!metricSums.has(key)) {
          metricSums.set(key, new Map());
          metricCounts.set(key, new Map());
          metadata.set(key, {
            display_id: row.displayId,
            agent_id: row.agentId,
            variant_id: row.variantId,
            model: row.model,
            count: 0,
            status_counts: {},
          });
        }
        const sums = metricSums.get(key) as Map<string, number>;
        const counts = metricCounts.get(key) as Map<string, number>;
        const meta = metadata.get(key) as {
          display_id: string;
          agent_id: string;
          variant_id: string;
          model: string | null;
          count: number;
          status_counts: Record<string, number>;
        };
        meta.count += row.count;
        for (const [statusName, statusCount] of Object.entries(row.statusCounts)) {
          meta.status_counts[statusName] = (meta.status_counts[statusName] || 0) + asInt(statusCount, 0);
        }
        let primaryMetric: number | null = null;
        for (const [metricName, metricValue] of Object.entries(row.metrics)) {
          const numeric = Number(metricValue);
          if (!Number.isFinite(numeric)) {
            continue;
          }
          sums.set(metricName, (sums.get(metricName) || 0) + numeric);
          counts.set(metricName, (counts.get(metricName) || 0) + 1);
          if (primaryMetric === null) {
            primaryMetric = numeric;
          }
        }
        const rowKey = primaryDimension === "benchmark-first" ? row.taskId : row.displayId;
        const colKey = primaryDimension === "benchmark-first" ? row.displayId : row.taskId;
        if (primaryMetric !== null) {
          if (!matrix[rowKey]) {
            matrix[rowKey] = {};
          }
          matrix[rowKey][colKey] = primaryMetric;
        }
      }

      agents = Array.from(metricSums.entries()).map(([key, sums]) => {
        const counts = metricCounts.get(key) || new Map<string, number>();
        const meta = metadata.get(key) as {
          display_id: string;
          agent_id: string;
          variant_id: string;
          model: string | null;
          count: number;
          status_counts: Record<string, number>;
        };
        const metrics: Record<string, number> = {};
        for (const [metricName, total] of sums.entries()) {
          const count = Math.max(1, counts.get(metricName) || 1);
          metrics[metricName] = total / count;
        }
        const rankScore = Object.values(metrics).length > 0 ? Math.max(...Object.values(metrics)) : 0;
        const coverage = liveSummary.agents.find((agent) => agent.display_id === meta.display_id);
        return {
          display_id: meta.display_id,
          agent_id: meta.agent_id,
          variant_id: meta.variant_id,
          model: meta.model,
          metrics,
          rank_score: rankScore,
          count: meta.count,
          status_counts: meta.status_counts,
          scored_trials: coverage?.scored_trials || 0,
          metric_counts: coverage?.metric_counts || {},
        };
      });
      agents.sort((a, b) => Number(b.rank_score) - Number(a.rank_score) || String(a.display_id).localeCompare(String(b.display_id)));
    }

    const models = Array.from(new Set(identities.map((row) => row.model).filter((value): value is string => Boolean(value)))).sort();
    const completed = state.status === "completed" ? 1 : 0;
    const running = state.status === "running" ? 1 : 0;

    return {
      run_id: state.runId,
      experiment_id: state.experimentId,
      benchmark: state.benchmark,
      status: state.status,
      primary_dimension: primaryDimension,
      variant_count: identities.length,
      models,
      identities,
      global_progress: {
        done: progress.done,
        total: progress.total,
        failed: progress.failed,
        running,
        completed,
      },
      agents,
      matrix,
      scored_trials: liveSummary.scoredTrials,
      scored_trials_by_identity: liveSummary.scoredTrialsByIdentity,
      metric_counts: liveSummary.metricCounts,
      recoverable_trials: recoveryCounters.recoverableTrials,
      retried_trials: recoveryCounters.retriedTrials,
      recovered_trials: recoveryCounters.recoveredTrials,
      still_failing_trials: recoveryCounters.stillFailingTrials,
      unfinished_trials: recoveryCounters.unfinishedTrials,
    };
  }

  listRuns(opts: { experimentId?: string } = {}): JsonRecord[] {
    this.pollOnce();
    const out: JsonRecord[] = [];
    for (const state of this.runs.values()) {
      if (opts.experimentId && state.experimentId !== opts.experimentId) {
        continue;
      }
      const progress = this.computeProgress(state);
      const taskRows = this.collectTaskMonitorRows(state);
      const identities = this.collectRunIdentities(state);
      const models = Array.from(new Set(identities.map((row) => row.model).filter((value): value is string => Boolean(value)))).sort();
      const liveSignals = this.computeRunLiveSignals(state, taskRows);
      const attentionCount = liveSignals.attentionCount + (state.status === "cancelled" || state.status === "zombie" ? 1 : 0);
      const recoveryCounters = this.computeRecoveryCounters(state);
      out.push({
        run_id: state.runId,
        experiment_id: state.experimentId,
        benchmark: state.benchmark,
        status: state.status,
        status_reason: state.statusReason,
        done: progress.done,
        total: progress.total,
        failed: progress.failed,
        updated_at_ms: state.updatedAtMs,
        path: state.runDir,
        variant_count: identities.length,
        models,
        is_live: state.status === "running",
        stalled: liveSignals.stalled,
        attention_count: attentionCount,
        has_task_monitor: liveSignals.hasTaskMonitor,
        heartbeat_only: liveSignals.heartbeatOnly,
        last_progress_ts_ms: liveSignals.lastProgressTsMs,
        runner_alive: state.runnerAlive,
        observer_stale: state.observerStale,
        recoverable_trials: recoveryCounters.recoverableTrials,
        retried_trials: recoveryCounters.retriedTrials,
        recovered_trials: recoveryCounters.recoveredTrials,
        still_failing_trials: recoveryCounters.stillFailingTrials,
        unfinished_trials: recoveryCounters.unfinishedTrials,
      });
    }
    return out.sort((a, b) => {
      const attentionA = asInt(a.attention_count, 0) > 0 || a.status === "running" ? 1 : 0;
      const attentionB = asInt(b.attention_count, 0) > 0 || b.status === "running" ? 1 : 0;
      if (attentionA !== attentionB) {
        return attentionB - attentionA;
      }
      return asInt(b.updated_at_ms, 0) - asInt(a.updated_at_ms, 0);
    });
  }

  listExperiments(): JsonRecord[] {
    this.pollOnce();
    const grouped = new Map<string, JsonRecord>();
    for (const state of this.runs.values()) {
      const key = state.experimentId || state.runId;
      if (!grouped.has(key)) {
        grouped.set(key, {
          experiment_id: key,
          run_count: 0,
          running: 0,
          completed: 0,
          updated_at_ms: 0,
          benchmarks: new Set<string>(),
        });
      }
      const slot = grouped.get(key) as JsonRecord;
      slot.run_count = asInt(slot.run_count, 0) + 1;
      if (state.status === "running") {
        slot.running = asInt(slot.running, 0) + 1;
      }
      if (state.status === "completed") {
        slot.completed = asInt(slot.completed, 0) + 1;
      }
      slot.updated_at_ms = Math.max(asInt(slot.updated_at_ms, 0), state.updatedAtMs);
      (slot.benchmarks as Set<string>).add(state.benchmark);
    }

    const out = Array.from(grouped.values()).map((row) => ({
      experiment_id: row.experiment_id,
      run_count: asInt(row.run_count, 0),
      running: asInt(row.running, 0),
      completed: asInt(row.completed, 0),
      updated_at_ms: asInt(row.updated_at_ms, 0),
      benchmarks: Array.from(row.benchmarks as Set<string>).sort(),
    }));
    out.sort((a, b) => asInt(b.updated_at_ms, 0) - asInt(a.updated_at_ms, 0));
    return out;
  }

  runSnapshot(runId: string): JsonRecord | null {
    this.pollOnce();
    const state = this.runs.get(runId);
    if (!state) {
      return null;
    }
    const progress = this.computeProgress(state);
    const taskRows = this.collectTaskMonitorRows(state);
    const liveSignals = this.computeRunLiveSignals(state, taskRows);
    const identities = this.collectRunIdentities(state);
    const scoredTrials = taskRows.filter((row) => Object.keys(row.scorerMetrics || {}).length > 0).length;
    const effectiveAttempts = this.effectiveRecoveryRows(state);
    const recoveryCounters = this.computeRecoveryCounters(state, effectiveAttempts);
    const recoveredCount = recoveryCounters.recoveredTrials;
    const outstandingFailures = effectiveAttempts.filter((row) => {
      const taskResult = ((row.task_result as JsonRecord) || {}) as JsonRecord;
      return String(taskResult.status || row.status || "").trim().toLowerCase() !== "success";
    }).length;
    return {
      run_id: state.runId,
      experiment_id: state.experimentId,
      benchmark: state.benchmark,
      status: state.status,
      status_reason: state.statusReason,
      done: progress.done,
      total: progress.total,
      failed: progress.failed,
      summary: state.summary,
      plan: state.plan,
      task_monitor: taskRows.map((row) => ({
        task_id: row.taskId,
        agent_id: row.agentId,
        variant_id: row.variantId,
        sample_id: row.sampleId,
        model: row.model,
        status: row.status,
        step_count: row.stepCount,
        started_at_ms: row.startedAtMs,
        ended_at_ms: row.endedAtMs,
        duration_ms: row.durationMs,
        latest_action: row.latestAction,
        latest_observation: row.latestObservation,
        latest_message: row.latestMessage,
        scorer_metrics: row.scorerMetrics,
      })),
      controls: (state.profiling.controls as JsonRecord) || {},
      updated_at_ms: state.updatedAtMs,
      last_event_id: state.lastEventIndex > 0 ? `${state.runId}:${state.lastEventIndex}` : null,
      path: state.runDir,
      variant_count: identities.length,
      models: Array.from(new Set(identities.map((row) => row.model).filter((value): value is string => Boolean(value)))).sort(),
      planned_trials: asInt(state.plan.trial_count, 0) || progress.total,
      planned_tasks:
        (Array.isArray(state.plan.task_ids) ? state.plan.task_ids.length : 0) ||
        new Set(taskRows.map((row) => row.taskId)).size,
      visible_task_rows: taskRows.length,
      scored_trials: scoredTrials,
      retry_attempts: recoveryCounters.retriedTrials,
      recovered_count: recoveredCount,
      outstanding_failures: outstandingFailures,
      recoverable_trials: recoveryCounters.recoverableTrials,
      retried_trials: recoveryCounters.retriedTrials,
      recovered_trials: recoveryCounters.recoveredTrials,
      still_failing_trials: recoveryCounters.stillFailingTrials,
      unfinished_trials: recoveryCounters.unfinishedTrials,
      attention_task_count: liveSignals.attentionTaskCount,
      last_progress_ts_ms: liveSignals.lastProgressTsMs,
      last_metric_ts_ms: liveSignals.lastMetricTsMs,
      stalled: liveSignals.stalled,
      heartbeat_only: liveSignals.heartbeatOnly,
      runner_alive: state.runnerAlive,
      observer_stale: state.observerStale,
      identities,
    };
  }

  runSummary(opts: { runId: string; primaryDimension?: string }): JsonRecord | null {
    this.pollOnce();
    const state = this.runs.get(opts.runId);
    if (!state) {
      return null;
    }
    const primaryDimension = opts.primaryDimension === "benchmark-first" ? "benchmark-first" : "variant-first";
    return this.buildRunSummary(state, primaryDimension);
  }

  backfillEvents(opts: { runId: string; lastEventId?: string | null; limit?: number }): JsonRecord[] {
    const idx = parseEventId(opts.lastEventId);
    const limit = Math.max(1, Math.min(5000, asInt(opts.limit, 500)));
    const rows = this.db
      .prepare(
        `
          SELECT event_json FROM events
          WHERE run_id = ? AND event_index > ?
          ORDER BY event_index ASC
          LIMIT ?
        `,
      )
      .all(opts.runId, idx, limit) as Array<{ event_json: string }>;

    const out: JsonRecord[] = [];
    for (const row of rows) {
      const parsed = parseJsonObject(row.event_json);
      if (Object.keys(parsed).length > 0) {
        out.push(parsed);
      }
    }
    return out;
  }

  subscribe(runId: string, cb: (event: JsonRecord) => void): () => void {
    const key = `run:${runId}`;
    const handler = (event: JsonRecord) => cb(event);
    this.emitter.on(key, handler);
    return () => {
      this.emitter.off(key, handler);
    };
  }

  getPretaskEvents(opts: { runId: string; trialKey: string }): JsonRecord[] {
    const rows = this.db
      .prepare(
        `
          SELECT event_json FROM events
          WHERE run_id = ? AND trial_key = ? AND event_name LIKE 'pretask.%'
          ORDER BY event_index ASC
        `,
      )
      .all(opts.runId, opts.trialKey) as Array<{ event_json: string }>;

    const out: JsonRecord[] = [];
    for (const row of rows) {
      const parsed = parseJsonObject(row.event_json);
      if (Object.keys(parsed).length > 0) {
        out.push(parsed);
      }
    }
    return out;
  }

  private trialMatches(row: JsonRecord, trial: TrialKeyParts): boolean {
    const taskResult = ((row.task_result as JsonRecord) || {}) as JsonRecord;
    const payload = ((taskResult.payload as JsonRecord) || {}) as JsonRecord;
    const taskId = String(taskResult.task_id || "");
    const agentId = String(taskResult.agent_id || "");
    const sampleId = String(taskResult.sample_id || "");
    const variantId = String(payload.variant_id || "default");
    if (!taskId || !agentId || !sampleId) {
      return false;
    }
    if (taskId !== trial.taskId || agentId !== trial.agentId || sampleId !== trial.sampleId) {
      return false;
    }
    return !trial.variantId || variantId === trial.variantId;
  }

  private readRecovery(state: RunState): JsonRecord {
    return readJsonObject(state.recoveryPath);
  }

  private effectiveRecoveryRows(state: RunState): JsonRecord[] {
    const recovery = this.readRecovery(state);
    const attemptsByTrial = recovery.attempts_by_trial;
    const effectiveAttempts = recovery.effective_attempts;
    if (!attemptsByTrial || typeof attemptsByTrial !== "object" || Array.isArray(attemptsByTrial)) {
      return [];
    }
    if (!effectiveAttempts || typeof effectiveAttempts !== "object" || Array.isArray(effectiveAttempts)) {
      return [];
    }
    const out: JsonRecord[] = [];
    for (const [trialKey, bucket] of Object.entries(attemptsByTrial as JsonRecord)) {
      if (!Array.isArray(bucket)) {
        continue;
      }
      const effectiveId = String((effectiveAttempts as JsonRecord)[trialKey] || "").trim();
      if (!effectiveId) {
        continue;
      }
      const match = bucket.find((row) => {
        if (!row || typeof row !== "object" || Array.isArray(row)) {
          return false;
        }
        return String((row as JsonRecord).attempt_id || "") === effectiveId;
      });
      if (match && typeof match === "object" && !Array.isArray(match)) {
        out.push(match as JsonRecord);
      }
    }
    return out;
  }

  private trialAttemptHistory(state: RunState, trialKey: string): JsonRecord[] {
    const recovery = this.readRecovery(state);
    const attemptsByTrial = recovery.attempts_by_trial;
    if (!attemptsByTrial || typeof attemptsByTrial !== "object" || Array.isArray(attemptsByTrial)) {
      return [];
    }
    const bucket = (attemptsByTrial as JsonRecord)[trialKey];
    if (!Array.isArray(bucket)) {
      return [];
    }
    return bucket
      .filter((row) => row && typeof row === "object" && !Array.isArray(row))
      .map((row) => row as JsonRecord)
      .sort((lhs, rhs) => asInt(lhs.attempt_no, 0) - asInt(rhs.attempt_no, 0));
  }

  private computeRecoveryCounters(
    state: RunState,
    effectiveAttempts?: JsonRecord[],
  ): RecoveryCounters {
    const effectiveRows = effectiveAttempts || this.effectiveRecoveryRows(state);
    const recovery = this.readRecovery(state);
    const attemptsByTrial = recovery.attempts_by_trial;
    const plannedTrials = Math.max(0, asInt(state.plan.trial_count, 0) || this.computeProgress(state).total);
    const unfinishedTrials = Math.max(0, plannedTrials - effectiveRows.length);

    let retriedTrials = 0;
    let recoveredTrials = 0;
    let stillFailingTrials = 0;
    if (attemptsByTrial && typeof attemptsByTrial === "object" && !Array.isArray(attemptsByTrial)) {
      for (const [trialKey, bucket] of Object.entries(attemptsByTrial as JsonRecord)) {
        if (!Array.isArray(bucket) || bucket.length <= 1) {
          continue;
        }
        retriedTrials += 1;
        const effectiveId = String(((recovery.effective_attempts as JsonRecord) || {})[trialKey] || "").trim();
        const effectiveRow = bucket.find((row) => row && typeof row === "object" && !Array.isArray(row) && String((row as JsonRecord).attempt_id || "") === effectiveId);
        const effectiveStatus = String((((effectiveRow as JsonRecord)?.task_result as JsonRecord) || {}).status || (effectiveRow as JsonRecord)?.status || "").trim().toLowerCase();
        if (effectiveStatus === "success") {
          recoveredTrials += 1;
        } else {
          stillFailingTrials += 1;
        }
      }
    }

    const nonSuccessEffective = effectiveRows.filter((row) => {
      const taskResult = ((row.task_result as JsonRecord) || {}) as JsonRecord;
      return String(taskResult.status || row.status || "").trim().toLowerCase() !== "success";
    }).length;
    return {
      recoverableTrials: unfinishedTrials + nonSuccessEffective,
      retriedTrials,
      recoveredTrials,
      stillFailingTrials,
      unfinishedTrials,
    };
  }

  private loadTrialOutcome(state: RunState, trial: TrialKeyParts): JsonRecord | null {
    const effectiveRows = this.effectiveRecoveryRows(state);
    if (effectiveRows.length > 0) {
      for (const row of effectiveRows) {
        const taskResult = ((row.task_result as JsonRecord) || {}) as JsonRecord;
        const payload = ((taskResult.payload as JsonRecord) || {}) as JsonRecord;
        const matches =
          String(taskResult.task_id || "") === trial.taskId &&
          String(taskResult.agent_id || "") === trial.agentId &&
          String(taskResult.sample_id || "") === trial.sampleId &&
          String(payload.variant_id || "default") === trial.variantId;
        if (matches) {
          return {
            schema_version: row.schema_version,
            task_result: taskResult,
            scores: ((row.scores as JsonRecord) || {}) as JsonRecord,
            trace: ((row.trace as JsonRecord) || {}) as JsonRecord,
            attempt_id: row.attempt_id,
            attempt_no: row.attempt_no,
            effective: row.effective,
            failure_class: row.failure_class,
            supersedes_attempt_id: row.supersedes_attempt_id,
            superseded_by_attempt_id: row.superseded_by_attempt_id,
            retry_source: row.retry_source,
          };
        }
      }
    }

    const trialsPath = path.join(state.runDir, "trials.jsonl");
    if (fs.existsSync(trialsPath)) {
      try {
        const lines = fs.readFileSync(trialsPath, "utf-8").split(/\r?\n/);
        for (const line of lines) {
          const row = parseJsonObject(line);
          if (Object.keys(row).length === 0) {
            continue;
          }
          if (this.trialMatches(row, trial)) {
            return row;
          }
        }
      } catch {
        // ignore malformed trials file
      }
    }

    const outcomesPath = path.join(state.runDir, "outcomes.json");
    if (!fs.existsSync(outcomesPath)) {
      return null;
    }
    try {
      const parsed = JSON.parse(fs.readFileSync(outcomesPath, "utf-8"));
      if (!Array.isArray(parsed)) {
        return null;
      }
      for (const row of parsed) {
        if (!row || typeof row !== "object" || Array.isArray(row)) {
          continue;
        }
        const asRow = row as JsonRecord;
        if (this.trialMatches(asRow, trial)) {
          return asRow;
        }
      }
    } catch {
      return null;
    }
    return null;
  }

  getTrialDetails(opts: { runId: string; trialKey: string }): JsonRecord | null {
    this.pollOnce();
    const state = this.runs.get(opts.runId);
    if (!state) {
      return null;
    }
    const trial = parseTrialKey(opts.trialKey);
    if (!trial) {
      return {
        run_id: opts.runId,
        trial_key: opts.trialKey,
        detail_error: "invalid_trial_key",
      };
    }

    const rows = this.db
      .prepare(
        `
          SELECT event_name, event_json FROM events
          WHERE run_id = ? AND trial_key = ?
          ORDER BY event_index ASC
        `,
      )
      .all(opts.runId, opts.trialKey) as Array<{ event_name: string; event_json: string }>;

    let startEvent: JsonRecord | null = null;
    let finishEvent: JsonRecord | null = null;
    let errorEvent: JsonRecord | null = null;
    const agentStepEvents: JsonRecord[] = [];
    const modelIoEvents: JsonRecord[] = [];

    for (const row of rows) {
      const parsed = parseJsonObject(row.event_json);
      if (Object.keys(parsed).length === 0) {
        continue;
      }
      if (row.event_name === "runtime.trial.start" && !startEvent) {
        startEvent = parsed;
      } else if (row.event_name === "runtime.trial.finish") {
        finishEvent = parsed;
      } else if (row.event_name === "runtime.trial.error") {
        errorEvent = parsed;
      } else if (row.event_name === "runtime.agent.step") {
        agentStepEvents.push(parsed);
      } else if (row.event_name === "runtime.model.io") {
        modelIoEvents.push(parsed);
      }
    }

    const outcome = this.loadTrialOutcome(state, trial);
    const attemptHistory = this.trialAttemptHistory(state, opts.trialKey);
    const taskResult = ((outcome?.task_result as JsonRecord) || {}) as JsonRecord;
    const taskPayload = ((taskResult.payload as JsonRecord) || {}) as JsonRecord;
    const finishPayload = (((finishEvent?.payload as JsonRecord) || {}) as JsonRecord);
    const scores = ((outcome?.scores as JsonRecord) || (finishPayload.scores as JsonRecord) || {}) as JsonRecord;
    const trace = ((outcome?.trace as JsonRecord) || {}) as JsonRecord;
    const startPayload = (((startEvent?.payload as JsonRecord) || {}) as JsonRecord);

    return {
      run_id: opts.runId,
      trial_key: opts.trialKey,
      task_id: trial.taskId,
      agent_id: trial.agentId,
      variant_id: trial.variantId,
      sample_id: trial.sampleId,
      status: String(taskResult.status || finishEvent?.status || errorEvent?.status || ""),
      sample_input: startPayload.sample_input || taskPayload.sample_input || null,
      final_output: taskResult.final_output || finishPayload.final_output || null,
      scores,
      error: taskResult.error || errorEvent || null,
      trace,
      start_event: startEvent,
      finish_event: finishEvent,
      error_event: errorEvent,
      agent_step_events: agentStepEvents,
      model_io_events: modelIoEvents,
      attempt_history: attemptHistory,
      attempt_id: outcome?.attempt_id || null,
      attempt_no: outcome?.attempt_no || null,
      effective: outcome?.effective ?? true,
      failure_class: outcome?.failure_class || null,
      supersedes_attempt_id: outcome?.supersedes_attempt_id || null,
      superseded_by_attempt_id: outcome?.superseded_by_attempt_id || null,
      retry_source: outcome?.retry_source || null,
    };
  }

  experimentSummary(opts: { experimentId: string; primaryDimension?: string }): JsonRecord {
    const primaryDimension = opts.primaryDimension === "benchmark-first" ? "benchmark-first" : "variant-first";
    const runs = Array.from(this.runs.values()).filter((state) => state.experimentId === opts.experimentId);

    const metricSums = new Map<string, Map<string, number>>();
    const metricCounts = new Map<string, Map<string, number>>();
    const matrixSums = new Map<string, Map<string, number>>();
    const matrixCounts = new Map<string, Map<string, number>>();
    const metadata = new Map<string, { display_id: string; agent_id: string; variant_id: string; model: string | null }>();

    let globalDone = 0;
    let globalTotal = 0;
    let globalFailed = 0;
    let running = 0;
    let completed = 0;

    for (const state of runs) {
      const progress = this.computeProgress(state);
      globalDone += progress.done;
      globalTotal += progress.total;
      globalFailed += progress.failed;
      if (state.status === "running") {
        running += 1;
      } else {
        completed += 1;
      }

      if (!fs.existsSync(state.aggregatePath)) {
        continue;
      }
      const rows = this.collectIdentityRows(state);
      for (const row of rows) {
        const identityKey = makeIdentityKey({ agentId: row.agentId, variantId: row.variantId, model: row.model });
        if (!metricSums.has(identityKey)) {
          metricSums.set(identityKey, new Map());
          metricCounts.set(identityKey, new Map());
          metadata.set(identityKey, {
            display_id: row.displayId,
            agent_id: row.agentId,
            variant_id: row.variantId,
            model: row.model,
          });
        }

        const metricNames = metricSums.get(identityKey) as Map<string, number>;
        const metricCountNames = metricCounts.get(identityKey) as Map<string, number>;
        let primaryMetric: number | null = null;
        for (const [metricName, metricValue] of Object.entries(row.metrics)) {
          const numeric = Number(metricValue);
          if (!Number.isFinite(numeric)) {
            continue;
          }
          metricNames.set(metricName, (metricNames.get(metricName) || 0) + numeric);
          metricCountNames.set(metricName, (metricCountNames.get(metricName) || 0) + 1);
          if (primaryMetric === null) {
            primaryMetric = numeric;
          }
        }

        if (primaryMetric !== null) {
          if (!matrixSums.has(identityKey)) {
            matrixSums.set(identityKey, new Map());
            matrixCounts.set(identityKey, new Map());
          }
          const rowSums = matrixSums.get(identityKey) as Map<string, number>;
          const rowCounts = matrixCounts.get(identityKey) as Map<string, number>;
          const benchmark = state.benchmark || "custom";
          rowSums.set(benchmark, (rowSums.get(benchmark) || 0) + primaryMetric);
          rowCounts.set(benchmark, (rowCounts.get(benchmark) || 0) + 1);
        }
      }
    }

    const agents = Array.from(metricSums.entries()).map(([identityKey, sums]) => {
      const counts = metricCounts.get(identityKey) || new Map<string, number>();
      const meta = metadata.get(identityKey) || {
        display_id: identityKey,
        agent_id: "unknown",
        variant_id: "default",
        model: null,
      };
      const metrics: Record<string, number> = {};
      for (const [metricName, total] of sums.entries()) {
        const count = Math.max(1, counts.get(metricName) || 1);
        metrics[metricName] = total / count;
      }
      const rankScore = Object.values(metrics).length > 0 ? Math.max(...Object.values(metrics)) : 0;
      return {
        display_id: meta.display_id,
        agent_id: meta.agent_id,
        variant_id: meta.variant_id,
        model: meta.model,
        metrics,
        rank_score: rankScore,
      };
    });
    agents.sort((a, b) => b.rank_score - a.rank_score || String(a.display_id).localeCompare(String(b.display_id)));

    const variantFirstMatrix: Record<string, Record<string, number>> = {};
    for (const [identityKey, values] of matrixSums.entries()) {
      const counts = matrixCounts.get(identityKey) || new Map<string, number>();
      const meta = metadata.get(identityKey) || {
        display_id: identityKey,
      };
      variantFirstMatrix[meta.display_id] = {};
      for (const [benchmark, sum] of values.entries()) {
        const count = Math.max(1, counts.get(benchmark) || 1);
        variantFirstMatrix[meta.display_id][benchmark] = sum / count;
      }
    }

    const benchmarkFirstMatrix: Record<string, Record<string, number>> = {};
    for (const [displayId, benchmarkRows] of Object.entries(variantFirstMatrix)) {
      for (const [benchmark, value] of Object.entries(benchmarkRows)) {
        if (!benchmarkFirstMatrix[benchmark]) {
          benchmarkFirstMatrix[benchmark] = {};
        }
        benchmarkFirstMatrix[benchmark][displayId] = value;
      }
    }

    return {
      experiment_id: opts.experimentId,
      primary_dimension: primaryDimension,
      run_count: runs.length,
      global_progress: {
        done: globalDone,
        total: globalTotal,
        failed: globalFailed,
        running,
        completed,
      },
      agents,
      matrix: primaryDimension === "benchmark-first" ? benchmarkFirstMatrix : variantFirstMatrix,
      runs: runs
        .slice()
        .sort((a, b) => b.updatedAtMs - a.updatedAtMs)
        .map((state) => ({
          run_id: state.runId,
          benchmark: state.benchmark,
          status: state.status,
          updated_at_ms: state.updatedAtMs,
        })),
    };
  }
}

declare global {
  // eslint-disable-next-line no-var
  var __snowlMonitorStore__: RunMonitorStore | undefined;
}

export function getMonitorStore(): RunMonitorStore {
  if (!global.__snowlMonitorStore__) {
    const runtimeCfg = readRuntimeConfig();
    const store = new RunMonitorStore({
      projectDir: process.env.SNOWL_PROJECT_DIR || runtimeCfg.project_dir,
      pollIntervalSec: Number(process.env.SNOWL_POLL_INTERVAL_SEC || runtimeCfg.poll_interval_sec || 0.5),
      maxEventBuffer: 4000,
    });
    store.start();
    global.__snowlMonitorStore__ = store;
  }
  return global.__snowlMonitorStore__;
}
