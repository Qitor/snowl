"use client";

import { useQuery } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Activity, AlertTriangle, FlaskConical, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { MatrixHeatmap } from "@/components/matrix-heatmap";
import { PretaskDrawer } from "@/components/pretask-drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { VirtualLogViewer } from "@/components/virtual-log-viewer";
import type { ExperimentRow, RunRow, RunSnapshot, RuntimeEvent, SummaryResponse } from "@/lib/types";
import { formatDateTime, formatPercent, makeTrialKey } from "@/lib/utils";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status}): ${url}`);
  }
  return (await response.json()) as T;
}

function toPrettyText(value: unknown): string {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        return JSON.stringify(JSON.parse(trimmed), null, 2);
      } catch {
        // keep raw text when parsing fails
      }
    }
    return value.replace(/\\n/g, "\n");
  }
  try {
    return JSON.stringify(value ?? null, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function hasDisplayValue(value: unknown): boolean {
  if (value === null || value === undefined) {
    return false;
  }
  if (typeof value === "string") {
    return value.trim().length > 0 && value.trim() !== "null";
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.keys(value as Record<string, unknown>).length > 0;
  }
  return true;
}

type HealthResponse = {
  ok: boolean;
  project_dir: string;
};

function useRuntimeStream(runId: string) {
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const lastEventId = useRef<string>("");

  useEffect(() => {
    setEvents([]);
    setConnected(false);
    lastEventId.current = "";
    if (!runId) {
      return;
    }

    const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events/stream`);
    const onRuntime = (event: MessageEvent<string>) => {
      try {
        const parsed = JSON.parse(event.data) as RuntimeEvent;
        const eventId = String(parsed.event_id || "");
        if (eventId && eventId === lastEventId.current) {
          return;
        }
        if (eventId) {
          lastEventId.current = eventId;
        }
        setEvents((prev) => {
          const next = prev.concat(parsed);
          if (next.length > 20_000) {
            return next.slice(next.length - 20_000);
          }
          return next;
        });
      } catch {
        // ignore malformed chunks
      }
    };

    source.addEventListener("runtime", onRuntime as EventListener);
    source.onmessage = onRuntime;
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    return () => {
      source.close();
    };
  }, [runId]);

  return { events, connected };
}

export function Dashboard() {
  const [selectedExperiment, setSelectedExperiment] = useState("");
  const [selectedRun, setSelectedRun] = useState("");
  const [activeTab, setActiveTab] = useState<"overview" | "tasks" | "runtime">("overview");
  const [view, setView] = useState<"agent-first" | "benchmark-first">("agent-first");
  const [trialKeyInput, setTrialKeyInput] = useState("");
  const [selectedTrialKey, setSelectedTrialKey] = useState("");
  const [taskSearch, setTaskSearch] = useState("");
  const [taskStatusFilter, setTaskStatusFilter] = useState("all");
  const [runtimeSearch, setRuntimeSearch] = useState("");
  const [runtimeEventFilter, setRuntimeEventFilter] = useState("all");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTrialKey, setDrawerTrialKey] = useState("");

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => fetchJson<HealthResponse>("/api/health"),
    refetchInterval: 5_000,
  });

  const experimentsQuery = useQuery({
    queryKey: ["experiments"],
    queryFn: () => fetchJson<{ items: ExperimentRow[] }>("/api/experiments"),
    refetchInterval: 3_000,
  });

  const experiments = experimentsQuery.data?.items || [];
  const monitorProject = healthQuery.data?.project_dir || "(project unavailable)";

  useEffect(() => {
    if (!selectedExperiment && experiments.length > 0) {
      setSelectedExperiment(experiments[0].experiment_id);
    }
  }, [experiments, selectedExperiment]);

  const runsQuery = useQuery({
    queryKey: ["runs", selectedExperiment],
    queryFn: () => fetchJson<{ items: RunRow[] }>(`/api/runs?experiment_id=${encodeURIComponent(selectedExperiment)}`),
    enabled: Boolean(selectedExperiment),
    refetchInterval: 2_000,
  });

  const runs = runsQuery.data?.items || [];

  useEffect(() => {
    if (!selectedRun && runs.length > 0) {
      setSelectedRun(runs[0].run_id);
      return;
    }
    if (selectedRun && runs.length > 0 && !runs.some((row) => row.run_id === selectedRun)) {
      setSelectedRun(runs[0].run_id);
    }
  }, [runs, selectedRun]);

  useEffect(() => {
    setSelectedTrialKey("");
    setTrialKeyInput("");
  }, [selectedRun]);

  const summaryQuery = useQuery({
    queryKey: ["summary", selectedExperiment, view],
    queryFn: () =>
      fetchJson<SummaryResponse>(
        `/api/experiments/${encodeURIComponent(selectedExperiment)}/summary?view=${encodeURIComponent(view)}`,
      ),
    enabled: Boolean(selectedExperiment),
    refetchInterval: 3_000,
  });

  const snapshotQuery = useQuery({
    queryKey: ["snapshot", selectedRun],
    queryFn: () => fetchJson<RunSnapshot>(`/api/runs/${encodeURIComponent(selectedRun)}/snapshot`),
    enabled: Boolean(selectedRun),
    refetchInterval: 2_000,
  });

  const pretaskQuery = useQuery({
    queryKey: ["pretask", selectedRun, drawerTrialKey, drawerOpen],
    queryFn: () =>
      fetchJson<{ items: Array<Record<string, unknown>> }>(
        `/api/runs/${encodeURIComponent(selectedRun)}/pretask?trial_key=${encodeURIComponent(drawerTrialKey)}`,
      ),
    enabled: Boolean(drawerOpen && selectedRun && drawerTrialKey),
    refetchInterval: drawerOpen ? 2_000 : false,
  });

  const trialDetailQuery = useQuery({
    queryKey: ["trial-detail", selectedRun, selectedTrialKey],
    queryFn: () =>
      fetchJson<Record<string, unknown>>(
        `/api/runs/${encodeURIComponent(selectedRun)}/trial?trial_key=${encodeURIComponent(selectedTrialKey)}`,
      ),
    enabled: Boolean(selectedRun && selectedTrialKey),
    refetchInterval: selectedTrialKey ? 2_000 : false,
  });

  const { events, connected } = useRuntimeStream(selectedRun);

  const progress = summaryQuery.data?.global_progress || {
    done: 0,
    total: 0,
    running: 0,
    completed: 0,
    failed: 0,
  };

  const completionRate = progress.total > 0 ? progress.done / progress.total : 0;

  const topAgents = summaryQuery.data?.agents.slice(0, 6) || [];

  const taskRows = useMemo(() => {
    const raw = snapshotQuery.data?.task_monitor;
    if (!Array.isArray(raw)) {
      return [] as Array<Record<string, unknown>>;
    }
    return raw;
  }, [snapshotQuery.data?.task_monitor]);

  const filteredTaskRows = useMemo(() => {
    const q = taskSearch.trim().toLowerCase();
    return taskRows.filter((row) => {
      const taskId = String(row.task_id || "-");
      const agentId = String(row.agent_id || "-");
      const variantId = String(row.variant_id || "default");
      const sampleId = row.sample_id == null ? "-" : String(row.sample_id);
      const status = String(row.status || "queued").toLowerCase();
      if (taskStatusFilter !== "all" && status !== taskStatusFilter) {
        return false;
      }
      if (!q) {
        return true;
      }
      const trialKey = makeTrialKey({
        task_id: taskId,
        agent_id: agentId,
        variant_id: variantId,
        sample_id: sampleId,
      }).toLowerCase();
      const haystack = `${trialKey} ${taskId} ${agentId} ${variantId} ${sampleId} ${status}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [taskRows, taskSearch, taskStatusFilter]);

  const filteredRuntimeEvents = useMemo(() => {
    const q = runtimeSearch.trim().toLowerCase();
    return events.filter((event) => {
      const eventName = String(event.event || "").toLowerCase();
      const message = String(event.message || "").toLowerCase();
      const raw = JSON.stringify(event).toLowerCase();
      if (runtimeEventFilter !== "all") {
        if (runtimeEventFilter === "pretask" && !eventName.startsWith("pretask.")) {
          return false;
        }
        if (runtimeEventFilter === "trial" && !(eventName.includes("trial") || eventName.includes("task"))) {
          return false;
        }
        if (runtimeEventFilter === "model" && !eventName.includes("model")) {
          return false;
        }
        if (runtimeEventFilter === "error") {
          const hasError = eventName.includes("error") || eventName.includes("failed") || message.includes("error");
          if (!hasError) {
            return false;
          }
        }
      }
      if (!q) {
        return true;
      }
      return `${eventName} ${message} ${raw}`.includes(q);
    });
  }, [events, runtimeSearch, runtimeEventFilter]);

  const taskContainerRef = useRef<HTMLDivElement | null>(null);
  const taskVirtualizer = useVirtualizer({
    count: filteredTaskRows.length,
    getScrollElement: () => taskContainerRef.current,
    estimateSize: () => 98,
    measureElement: (el) => el?.getBoundingClientRect().height ?? 0,
    overscan: 12,
  });

  const runSnapshotCard = (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Run Snapshot</CardTitle>
      </CardHeader>
      <CardContent className="text-base text-muted-foreground">
        <div className="grid gap-2 md:grid-cols-3">
          <div className="rounded border p-2">
            <div className="mb-1 flex items-center gap-1 text-foreground">
              <Activity className="h-4 w-4" />
              状态
            </div>
            <div>status={snapshotQuery.data?.status || "-"}</div>
            <div>progress={snapshotQuery.data?.done || 0}/{snapshotQuery.data?.total || 0}</div>
          </div>
          <div className="rounded border p-2">
            <div className="mb-1 text-foreground">事件游标</div>
            <div className="font-[family-name:var(--font-mono)]">{snapshotQuery.data?.last_event_id || "-"}</div>
          </div>
          <div className="rounded border p-2">
            <div className="mb-1 flex items-center gap-1 text-foreground">
              <AlertTriangle className="h-4 w-4" />
              更新时间
            </div>
            <div>{formatDateTime(snapshotQuery.data?.updated_at_ms)}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  const taskMonitorCard = (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-xl">L3 任务级监控</CardTitle>
            <CardDescription>状态 / 阶段耗时 / 失败定位</CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={() => snapshotQuery.refetch()}>
            <RefreshCw className="mr-1 h-4 w-4" />
            刷新
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_200px_auto]">
          <Input
            value={taskSearch}
            onChange={(event) => setTaskSearch(event.target.value)}
            placeholder="搜索 task / agent / variant / sample / trial key"
            className="text-base"
          />
          <Select
            value={taskStatusFilter}
            onChange={(event) => setTaskStatusFilter(event.target.value)}
            className="text-base"
          >
            <option value="all">all status</option>
            <option value="queued">queued</option>
            <option value="running">running</option>
            <option value="success">success</option>
            <option value="error">error</option>
          </Select>
          <div className="flex items-center rounded-md border bg-muted/40 px-3 text-sm text-muted-foreground">
            matched {filteredTaskRows.length}/{taskRows.length}
          </div>
        </div>
        <div ref={taskContainerRef} className="h-[460px] overflow-auto rounded-md border">
          <div style={{ height: `${taskVirtualizer.getTotalSize()}px`, position: "relative" }}>
            {taskVirtualizer.getVirtualItems().map((item) => {
              const row = filteredTaskRows[item.index] || {};
              const taskId = String(row.task_id || "-");
              const agentId = String(row.agent_id || "-");
              const variantId = String(row.variant_id || "default");
              const sampleId = row.sample_id == null ? "-" : String(row.sample_id);
              const status = String(row.status || "queued");
              const durationMs = Number(row.duration_ms || 0);
              const statusVariant = (status === "success"
                ? "success"
                : status === "error"
                  ? "danger"
                  : status === "running"
                    ? "warning"
                    : "outline") as "success" | "danger" | "warning" | "outline";
              const localTrialKey = makeTrialKey({
                task_id: taskId,
                agent_id: agentId,
                variant_id: variantId,
                sample_id: sampleId,
              });

              return (
                <div
                  key={`${localTrialKey}-${item.index}`}
                  ref={taskVirtualizer.measureElement}
                  data-index={item.index}
                  className={`absolute left-0 top-0 w-full border-b px-3 py-3 ${item.index % 2 === 0 ? "bg-card/65" : "bg-card/40"}`}
                  style={{ transform: `translateY(${item.start}px)` }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="font-[family-name:var(--font-mono)] text-base leading-6 whitespace-normal break-all">{localTrialKey}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                        <Badge variant={statusVariant}>{status}</Badge>
                        <span>duration={durationMs}ms</span>
                        <span className="font-[family-name:var(--font-mono)]">task={taskId}</span>
                        <span className="font-[family-name:var(--font-mono)]">sample={sampleId}</span>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2 self-start">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setSelectedTrialKey(localTrialKey);
                          setTrialKeyInput(localTrialKey);
                        }}
                      >
                        查看详情
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setDrawerTrialKey(localTrialKey);
                          setTrialKeyInput(localTrialKey);
                          setDrawerOpen(true);
                        }}
                      >
                        Pretask
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {filteredTaskRows.length === 0 ? (
            <div className="p-4 text-sm text-muted-foreground">没有匹配项，试试放宽关键字或切换状态筛选。</div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );

  const runtimeEventsCard = (
    <Card>
      <CardHeader>
        <CardTitle className="text-2xl">L4 Live Runtime Events</CardTitle>
        <CardDescription className="text-base">日志诊断入口（支持断线续传）</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_200px_auto]">
          <Input
            value={runtimeSearch}
            onChange={(event) => setRuntimeSearch(event.target.value)}
            placeholder="搜索 event / message / task / agent / trial key"
            className="text-base"
          />
          <Select
            value={runtimeEventFilter}
            onChange={(event) => setRuntimeEventFilter(event.target.value)}
            className="text-base"
          >
            <option value="all">all events</option>
            <option value="pretask">pretask.*</option>
            <option value="trial">trial/task</option>
            <option value="model">model*</option>
            <option value="error">errors only</option>
          </Select>
          <div className="flex items-center rounded-md border bg-muted/40 px-3 text-sm text-muted-foreground">
            matched {filteredRuntimeEvents.length}/{events.length}
          </div>
        </div>
        <VirtualLogViewer events={filteredRuntimeEvents} />
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <Input
            value={trialKeyInput}
            onChange={(e) => setTrialKeyInput(e.target.value)}
            placeholder="task::agent::variant::sample"
            className="font-[family-name:var(--font-mono)] text-base"
          />
          <Button
            variant="outline"
            onClick={() => {
              if (!trialKeyInput.trim()) {
                return;
              }
              setSelectedTrialKey(trialKeyInput.trim());
            }}
          >
            查看详情
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              if (!trialKeyInput.trim()) {
                return;
              }
              setDrawerTrialKey(trialKeyInput.trim());
              setDrawerOpen(true);
            }}
          >
            打开 Pretask
          </Button>
        </div>
      </CardContent>
    </Card>
  );

  const trialDetail = trialDetailQuery.data || null;
  const trialScores = ((trialDetail?.scores as Record<string, unknown> | undefined) || {}) as Record<string, unknown>;
  const trialStatus = String((trialDetail?.status as string | undefined) || "");
  const trialSections = [
    { key: "payload", title: "Task Payload", value: trialDetail?.sample_input },
    { key: "result", title: "Result Artifact", value: trialDetail?.final_output },
    { key: "trace", title: "Execution Trace", value: trialDetail?.trace },
    { key: "start", title: "Runtime Start Event", value: trialDetail?.start_event },
    { key: "finish", title: "Runtime Finish Event", value: trialDetail?.finish_event },
    { key: "error", title: "Error Diagnostics", value: trialDetail?.error ?? trialDetail?.error_event },
  ].filter((section) => hasDisplayValue(section.value));
  const trialDetailCard = (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="text-xl">Trial Detail</CardTitle>
            <CardDescription className="font-[family-name:var(--font-mono)] text-sm whitespace-normal break-all">
              {selectedTrialKey ? `trial=${selectedTrialKey}` : "选择一个 task::agent::variant::sample 查看任务细节"}
            </CardDescription>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              if (!selectedTrialKey) {
                return;
              }
              setDrawerTrialKey(selectedTrialKey);
              setDrawerOpen(true);
            }}
            disabled={!selectedTrialKey}
          >
            打开 Pretask
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {!selectedTrialKey ? (
          <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            在 L3 里点击“查看详情”，或在 Runtime 输入 trial key。
          </div>
        ) : null}
        {selectedTrialKey && trialDetailQuery.isLoading ? <div className="text-sm text-muted-foreground">加载详情中...</div> : null}
        {selectedTrialKey && trialDetailQuery.isError ? (
          <div className="rounded-md border border-dashed p-3 text-sm text-danger">加载详情失败，请重试。</div>
        ) : null}
        {selectedTrialKey && !trialDetailQuery.isLoading && !trialDetailQuery.isError ? (
          <>
            <div className="flex flex-wrap items-center gap-2 text-base">
              <Badge variant={trialStatus === "success" ? "success" : trialStatus === "error" ? "danger" : "warning"}>
                {trialStatus || "unknown"}
              </Badge>
              <span className="font-[family-name:var(--font-mono)] whitespace-normal break-all text-muted-foreground">
                task={String((trialDetail?.task_id as string | undefined) || "-")}
              </span>
              <span className="font-[family-name:var(--font-mono)] whitespace-normal break-all text-muted-foreground">
                agent={String((trialDetail?.agent_id as string | undefined) || "-")}
              </span>
            </div>
            {Object.keys(trialScores).length > 0 ? (
              <div className="space-y-2 rounded-md border bg-muted/20 p-3">
                <div className="text-sm font-medium text-muted-foreground">Score Breakdown</div>
                <div className="grid gap-2 md:grid-cols-2">
                  {Object.entries(trialScores).map(([key, value]) => (
                    <div key={key} className="rounded-md border bg-background p-2">
                      <div className="font-[family-name:var(--font-mono)] text-sm font-semibold">{key}</div>
                      <pre className="mt-1 max-h-[180px] overflow-auto text-sm leading-6 whitespace-pre-wrap break-all text-foreground/90">
                        {toPrettyText(value)}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="grid gap-3">
              {trialSections.length === 0 ? (
                <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">暂无可展示字段。</div>
              ) : (
                trialSections.map((section) => (
                  <div key={section.key} className="rounded-md border bg-background p-3">
                    <div className="mb-1 text-sm font-medium text-muted-foreground">{section.title}</div>
                    <pre className="max-h-[280px] overflow-auto rounded border bg-slate-950 px-3 py-2 text-sm leading-7 whitespace-pre-wrap break-all text-cyan-100">
                      {toPrettyText(section.value)}
                    </pre>
                  </div>
                ))
              )}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );

  return (
    <main className="mx-auto max-w-[1860px] px-5 py-6 md:px-10 md:py-8">
      <header className="mb-6 rounded-2xl border bg-gradient-to-r from-emerald-50/95 via-cyan-50/95 to-sky-100/90 p-7 shadow">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-4xl font-semibold tracking-tight md:text-5xl">Snowl Experiment Console</h1>
            <p className="text-lg leading-relaxed text-muted-foreground">
              CLI 发起评测，Web 实时观察与诊断。支持 agent / benchmark 双视角与 pretask 全链路追踪。
            </p>
            <p className="mt-1 font-[family-name:var(--font-mono)] text-base text-muted-foreground">project={monitorProject}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={connected ? "success" : "warning"}>{connected ? "SSE Connected" : "SSE Reconnecting"}</Badge>
            <Badge variant="outline">events {events.length}</Badge>
          </div>
        </div>
      </header>

      <div className="grid gap-4 xl:grid-cols-12">
        <section className="space-y-4 xl:col-span-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Experiments</CardTitle>
              <CardDescription>L1 总览入口</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="max-h-[280px] space-y-2 overflow-auto pr-1">
                {experiments.map((row) => {
                  const active = row.experiment_id === selectedExperiment;
                  return (
                    <button
                      key={row.experiment_id}
                      className={`w-full rounded-lg border p-3 text-left transition ${
                        active ? "border-primary bg-primary/10" : "hover:bg-muted/70"
                      }`}
                      onClick={() => {
                        setSelectedExperiment(row.experiment_id);
                        setSelectedRun("");
                      }}
                    >
                      <div className="font-[family-name:var(--font-mono)] text-base">{row.experiment_id}</div>
                      <div className="mt-1 flex flex-wrap gap-1 text-sm">
                        <Badge variant="outline">runs {row.run_count}</Badge>
                        <Badge variant="warning">running {row.running}</Badge>
                        <Badge variant="success">done {row.completed}</Badge>
                      </div>
                    </button>
                  );
                })}
                {experiments.length === 0 ? (
                  <div className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
                    当前监控目录暂无运行记录：{monitorProject}/.snowl/runs
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Runs</CardTitle>
              <CardDescription>L2 运行矩阵入口</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="max-h-[300px] space-y-2 overflow-auto pr-1">
                {runs.map((run) => {
                  const active = run.run_id === selectedRun;
                  const complete = run.total > 0 ? run.done / run.total : 0;
                  return (
                    <button
                      key={run.run_id}
                      className={`w-full rounded-lg border p-3 text-left transition ${
                        active ? "border-primary bg-primary/10" : "hover:bg-muted/70"
                      }`}
                      onClick={() => setSelectedRun(run.run_id)}
                    >
                      <div className="font-[family-name:var(--font-mono)] text-base">{run.run_id}</div>
                      <div className="mt-1 flex flex-wrap gap-1 text-sm">
                        <Badge variant="outline">{run.benchmark}</Badge>
                        <Badge variant={run.status === "completed" ? "success" : "warning"}>{run.status}</Badge>
                        <Badge variant="outline">
                          {run.done}/{run.total}
                        </Badge>
                      </div>
                      <div className="mt-2 h-2 rounded bg-muted">
                        <div className="h-2 rounded bg-primary" style={{ width: `${Math.max(4, complete * 100)}%` }} />
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="space-y-4 xl:col-span-9">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <CardTitle className="text-xl">Workspace</CardTitle>
                  <CardDescription>
                    exp={selectedExperiment || "-"} | run={selectedRun || "-"}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-base text-muted-foreground">primary view</label>
                  <Select
                    value={view}
                    onChange={(e) => setView((e.target.value as "agent-first" | "benchmark-first") || "agent-first")}
                    className="w-[180px]"
                  >
                    <option value="agent-first">agent-first</option>
                    <option value="benchmark-first">benchmark-first</option>
                  </Select>
                </div>
              </div>
              <div className="mt-2 rounded-2xl border bg-muted/55 p-2">
                <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                {[
                  { key: "overview", label: "Overview", hint: "L1 + L2" },
                  { key: "tasks", label: "Tasks", hint: `L3 (${taskRows.length})` },
                  { key: "runtime", label: "Runtime", hint: `logs (${events.length})` },
                ].map((tab) => {
                  const active = activeTab === tab.key;
                  return (
                    <button
                      key={tab.key}
                      onClick={() => setActiveTab(tab.key as "overview" | "tasks" | "runtime")}
                      className={`min-h-[56px] rounded-xl border px-4 py-2.5 text-left text-base font-semibold tracking-tight transition ${
                        active
                          ? "border-primary bg-primary text-primary-foreground shadow"
                          : "border-border/80 bg-card/50 text-muted-foreground hover:bg-card/80 hover:text-foreground"
                      }`}
                    >
                      <div>{tab.label}</div>
                      <div className={`text-sm ${active ? "opacity-95" : "opacity-85"}`}>{tab.hint}</div>
                    </button>
                  );
                })}
                </div>
              </div>
            </CardHeader>
          </Card>

          {activeTab === "overview" ? (
            <>
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-xl">L1 实验总览</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 md:grid-cols-5">
                    <div className="rounded-lg border bg-background/70 p-3">
                      <div className="text-base text-muted-foreground">Overall Progress</div>
                      <div className="mt-2 text-3xl font-semibold">{formatPercent(completionRate)}</div>
                      <div className="mt-1 text-sm text-muted-foreground">
                        {progress.done}/{progress.total}
                      </div>
                    </div>
                    <div className="rounded-lg border bg-background/70 p-3">
                      <div className="text-base text-muted-foreground">Running</div>
                      <div className="mt-2 text-3xl font-semibold text-warning">{progress.running}</div>
                    </div>
                    <div className="rounded-lg border bg-background/70 p-3">
                      <div className="text-base text-muted-foreground">Completed</div>
                      <div className="mt-2 text-3xl font-semibold text-success">{progress.completed}</div>
                    </div>
                    <div className="rounded-lg border bg-background/70 p-3">
                      <div className="text-base text-muted-foreground">Failed</div>
                      <div className="mt-2 text-3xl font-semibold text-danger">{progress.failed}</div>
                    </div>
                    <div className="rounded-lg border bg-background/70 p-3">
                      <div className="text-base text-muted-foreground">Run Count</div>
                      <div className="mt-2 text-3xl font-semibold">{summaryQuery.data?.run_count || 0}</div>
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="mb-2 flex items-center gap-2 text-base font-medium">
                      <FlaskConical className="h-4 w-4 text-primary" />
                      agent ranking
                    </div>
                    <div className="grid gap-2 md:grid-cols-2">
                      {topAgents.length === 0 ? (
                        <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">暂无 ranking 数据。</div>
                      ) : (
                        topAgents.map((agent) => (
                          <div key={agent.agent_id} className="rounded-lg border p-3">
                            <div className="font-[family-name:var(--font-mono)] text-base">{agent.agent_id}</div>
                            <div className="mt-1 flex items-center justify-between text-base">
                              <span className="text-muted-foreground">rank score</span>
                              <span className="font-semibold">{agent.rank_score.toFixed(4)}</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-xl">L2 运行矩阵</CardTitle>
                  <CardDescription>agent × benchmark 透视（可切换主维度）</CardDescription>
                </CardHeader>
                <CardContent>
                  {summaryQuery.isLoading ? (
                    <div className="text-sm text-muted-foreground">加载矩阵...</div>
                  ) : (
                    <MatrixHeatmap
                      matrix={summaryQuery.data?.matrix || {}}
                      rowLabel={view === "agent-first" ? "Agent" : "Benchmark"}
                      colLabel={view === "agent-first" ? "Benchmark" : "Agent"}
                    />
                  )}
                </CardContent>
              </Card>
              {runSnapshotCard}
            </>
          ) : null}

          {activeTab === "tasks" ? (
            <>
              {taskMonitorCard}
              {trialDetailCard}
              {runSnapshotCard}
            </>
          ) : null}

          {activeTab === "runtime" ? (
            <>
              {runtimeEventsCard}
              {trialDetailCard}
              {runSnapshotCard}
            </>
          ) : null}
        </section>
      </div>

      <PretaskDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        runId={selectedRun}
        trialKey={drawerTrialKey}
        items={pretaskQuery.data?.items || []}
        loading={pretaskQuery.isLoading}
      />
    </main>
  );
}
