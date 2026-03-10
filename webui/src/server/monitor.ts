import { EventEmitter } from "node:events";
import fs from "node:fs";
import path from "node:path";

import Database from "better-sqlite3";

type JsonRecord = Record<string, unknown>;

type RunState = {
  runId: string;
  runDir: string;
  eventsPath: string;
  manifestPath: string;
  summaryPath: string;
  planPath: string;
  aggregatePath: string;
  profilingPath: string;
  eventPos: number;
  eventTail: string;
  lastEventIndex: number;
  updatedAtMs: number;
  status: "running" | "completed";
  experimentId: string;
  benchmark: string;
  summary: JsonRecord;
  plan: JsonRecord;
  profiling: JsonRecord;
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

function normalizeDimension(value: string | null | undefined): "agent-first" | "benchmark-first" {
  return value === "benchmark-first" ? "benchmark-first" : "agent-first";
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

  private inferBenchmark(manifest: JsonRecord, profiling: JsonRecord): string {
    const runMeta = (profiling.run as JsonRecord) || {};
    const fromRun = String(runMeta.benchmark || "").trim().toLowerCase();
    if (fromRun) {
      return fromRun;
    }
    const fromManifest = String(manifest.benchmark || "").trim().toLowerCase();
    return fromManifest || "custom";
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
    state.summary = readJsonObject(state.summaryPath);
    state.plan = readJsonObject(state.planPath);
    state.profiling = readJsonObject(state.profilingPath);
    state.experimentId = this.inferExperimentId(state.runId, manifest, state.profiling);
    state.benchmark = this.inferBenchmark(manifest, state.profiling);
    state.status = Object.keys(state.summary).length > 0 ? "completed" : "running";
    state.updatedAtMs = nowMs();
    this.upsertRunRow(state, manifest);
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
      state.updatedAtMs = nowMs();
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
          eventsPath: path.join(pointer.runDir, "events.jsonl"),
          manifestPath: path.join(pointer.runDir, "manifest.json"),
          summaryPath: path.join(pointer.runDir, "summary.json"),
          planPath: path.join(pointer.runDir, "plan.json"),
          aggregatePath: path.join(pointer.runDir, "aggregate.json"),
          profilingPath: path.join(pointer.runDir, "profiling.json"),
          eventPos: 0,
          eventTail: "",
          lastEventIndex: 0,
          updatedAtMs: nowMs(),
          status: "running",
          experimentId: pointer.runId,
          benchmark: "custom",
          summary: {},
          plan: {},
          profiling: {},
        });
        discovered += 1;
      } else if (existing.runDir !== pointer.runDir) {
        existing.runDir = pointer.runDir;
        existing.eventsPath = path.join(pointer.runDir, "events.jsonl");
        existing.manifestPath = path.join(pointer.runDir, "manifest.json");
        existing.summaryPath = path.join(pointer.runDir, "summary.json");
        existing.planPath = path.join(pointer.runDir, "plan.json");
        existing.aggregatePath = path.join(pointer.runDir, "aggregate.json");
        existing.profilingPath = path.join(pointer.runDir, "profiling.json");
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
    if (state.summary && Object.keys(state.summary).length > 0) {
      const total = asInt(state.summary.total, 0);
      const failed = asInt(state.summary.error, 0) + asInt(state.summary.limit_exceeded, 0) + asInt(state.summary.cancelled, 0);
      return { done: total, total, failed };
    }
    const total = asInt(state.plan.trial_count, 0);
    const doneRow = this.db
      .prepare("SELECT COUNT(*) AS c FROM events WHERE run_id = ? AND event_name='runtime.trial.finish'")
      .get(state.runId) as { c?: number };
    const failRow = this.db
      .prepare("SELECT COUNT(*) AS c FROM events WHERE run_id = ? AND event_name='runtime.trial.error'")
      .get(state.runId) as { c?: number };
    return { done: asInt(doneRow?.c, 0), total, failed: asInt(failRow?.c, 0) };
  }

  listRuns(opts: { experimentId?: string } = {}): JsonRecord[] {
    this.pollOnce();
    const out: JsonRecord[] = [];
    for (const state of this.runs.values()) {
      if (opts.experimentId && state.experimentId !== opts.experimentId) {
        continue;
      }
      const progress = this.computeProgress(state);
      out.push({
        run_id: state.runId,
        experiment_id: state.experimentId,
        benchmark: state.benchmark,
        status: state.status,
        done: progress.done,
        total: progress.total,
        failed: progress.failed,
        updated_at_ms: state.updatedAtMs,
        path: state.runDir,
      });
    }
    return out.sort((a, b) => asInt(b.updated_at_ms, 0) - asInt(a.updated_at_ms, 0));
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
    return {
      run_id: state.runId,
      experiment_id: state.experimentId,
      benchmark: state.benchmark,
      status: state.status,
      done: progress.done,
      total: progress.total,
      failed: progress.failed,
      summary: state.summary,
      plan: state.plan,
      task_monitor: Array.isArray(state.profiling.task_monitor) ? state.profiling.task_monitor : [],
      controls: (state.profiling.controls as JsonRecord) || {},
      updated_at_ms: state.updatedAtMs,
      last_event_id: state.lastEventIndex > 0 ? `${state.runId}:${state.lastEventIndex}` : null,
      path: state.runDir,
    };
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

  private loadTrialOutcome(state: RunState, trial: TrialKeyParts): JsonRecord | null {
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
      }
    }

    const outcome = this.loadTrialOutcome(state, trial);
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
    };
  }

  experimentSummary(opts: { experimentId: string; primaryDimension?: string }): JsonRecord {
    const primaryDimension = normalizeDimension(opts.primaryDimension);
    const runs = Array.from(this.runs.values()).filter((state) => state.experimentId === opts.experimentId);

    const metricSums = new Map<string, Map<string, number>>();
    const metricCounts = new Map<string, Map<string, number>>();
    const matrixSums = new Map<string, Map<string, number>>();
    const matrixCounts = new Map<string, Map<string, number>>();

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
      const aggregate = readJsonObject(state.aggregatePath);
      const byTaskAgent = (aggregate.by_task_agent as JsonRecord) || {};
      for (const row of Object.values(byTaskAgent)) {
        if (!row || typeof row !== "object" || Array.isArray(row)) {
          continue;
        }
        const asRow = row as JsonRecord;
        const agentId = String(asRow.agent_id || "unknown");
        const metrics = (asRow.metrics as JsonRecord) || {};

        let metricNames = metricSums.get(agentId);
        if (!metricNames) {
          metricNames = new Map();
          metricSums.set(agentId, metricNames);
        }
        let metricCountNames = metricCounts.get(agentId);
        if (!metricCountNames) {
          metricCountNames = new Map();
          metricCounts.set(agentId, metricCountNames);
        }

        let primaryMetric: number | null = null;
        for (const [metricName, metricValue] of Object.entries(metrics)) {
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
          if (!matrixSums.has(agentId)) {
            matrixSums.set(agentId, new Map());
            matrixCounts.set(agentId, new Map());
          }
          const agentRow = matrixSums.get(agentId) as Map<string, number>;
          const agentCount = matrixCounts.get(agentId) as Map<string, number>;
          const benchmark = state.benchmark || "custom";
          agentRow.set(benchmark, (agentRow.get(benchmark) || 0) + primaryMetric);
          agentCount.set(benchmark, (agentCount.get(benchmark) || 0) + 1);
        }
      }
    }

    const agents = Array.from(metricSums.entries()).map(([agentId, sums]) => {
      const counts = metricCounts.get(agentId) || new Map<string, number>();
      const metrics: Record<string, number> = {};
      for (const [metricName, total] of sums.entries()) {
        const count = Math.max(1, counts.get(metricName) || 1);
        metrics[metricName] = total / count;
      }
      const rankScore = Object.values(metrics).length > 0 ? Math.max(...Object.values(metrics)) : 0;
      return {
        agent_id: agentId,
        metrics,
        rank_score: rankScore,
      };
    });
    agents.sort((a, b) => b.rank_score - a.rank_score);

    const agentFirstMatrix: Record<string, Record<string, number>> = {};
    for (const [agentId, values] of matrixSums.entries()) {
      const counts = matrixCounts.get(agentId) || new Map<string, number>();
      agentFirstMatrix[agentId] = {};
      for (const [benchmark, sum] of values.entries()) {
        const count = Math.max(1, counts.get(benchmark) || 1);
        agentFirstMatrix[agentId][benchmark] = sum / count;
      }
    }

    const benchmarkFirstMatrix: Record<string, Record<string, number>> = {};
    for (const [agentId, benchmarkRows] of Object.entries(agentFirstMatrix)) {
      for (const [benchmark, value] of Object.entries(benchmarkRows)) {
        if (!benchmarkFirstMatrix[benchmark]) {
          benchmarkFirstMatrix[benchmark] = {};
        }
        benchmarkFirstMatrix[benchmark][agentId] = value;
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
      matrix: primaryDimension === "benchmark-first" ? benchmarkFirstMatrix : agentFirstMatrix,
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
