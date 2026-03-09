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
  const [view, setView] = useState<"agent-first" | "benchmark-first">("agent-first");
  const [trialKeyInput, setTrialKeyInput] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTrialKey, setDrawerTrialKey] = useState("");

  const experimentsQuery = useQuery({
    queryKey: ["experiments"],
    queryFn: () => fetchJson<{ items: ExperimentRow[] }>("/api/experiments"),
    refetchInterval: 3_000,
  });

  const experiments = experimentsQuery.data?.items || [];

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

  const taskContainerRef = useRef<HTMLDivElement | null>(null);
  const taskVirtualizer = useVirtualizer({
    count: taskRows.length,
    getScrollElement: () => taskContainerRef.current,
    estimateSize: () => 54,
    overscan: 12,
  });

  return (
    <main className="mx-auto max-w-[1600px] px-4 py-4 md:px-6 md:py-6">
      <header className="mb-4 rounded-xl border bg-gradient-to-r from-emerald-50/80 via-cyan-50/80 to-sky-100/70 p-5 shadow-sm">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Snowl Experiment Console</h1>
            <p className="text-sm text-muted-foreground">
              CLI 发起评测，Web 实时观察与诊断。支持 agent / benchmark 双视角与 pretask 全链路追踪。
            </p>
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
              <CardTitle className="text-base">Experiments</CardTitle>
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
                      <div className="font-[family-name:var(--font-mono)] text-xs">{row.experiment_id}</div>
                      <div className="mt-1 flex flex-wrap gap-1 text-[11px]">
                        <Badge variant="outline">runs {row.run_count}</Badge>
                        <Badge variant="warning">running {row.running}</Badge>
                        <Badge variant="success">done {row.completed}</Badge>
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Runs</CardTitle>
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
                      <div className="font-[family-name:var(--font-mono)] text-xs">{run.run_id}</div>
                      <div className="mt-1 flex flex-wrap gap-1 text-[11px]">
                        <Badge variant="outline">{run.benchmark}</Badge>
                        <Badge variant={run.status === "completed" ? "success" : "warning"}>{run.status}</Badge>
                        <Badge variant="outline">
                          {run.done}/{run.total}
                        </Badge>
                      </div>
                      <div className="mt-2 h-1.5 rounded bg-muted">
                        <div className="h-1.5 rounded bg-primary" style={{ width: `${Math.max(4, complete * 100)}%` }} />
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
                  <CardTitle className="text-base">L1 实验总览</CardTitle>
                  <CardDescription>
                    exp={selectedExperiment || "-"} | run={selectedRun || "-"}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-muted-foreground">primary view</label>
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
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-5">
                <div className="rounded-lg border bg-background/70 p-3">
                  <div className="text-xs text-muted-foreground">Overall Progress</div>
                  <div className="mt-2 text-xl font-semibold">{formatPercent(completionRate)}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {progress.done}/{progress.total}
                  </div>
                </div>
                <div className="rounded-lg border bg-background/70 p-3">
                  <div className="text-xs text-muted-foreground">Running</div>
                  <div className="mt-2 text-xl font-semibold text-warning">{progress.running}</div>
                </div>
                <div className="rounded-lg border bg-background/70 p-3">
                  <div className="text-xs text-muted-foreground">Completed</div>
                  <div className="mt-2 text-xl font-semibold text-success">{progress.completed}</div>
                </div>
                <div className="rounded-lg border bg-background/70 p-3">
                  <div className="text-xs text-muted-foreground">Failed</div>
                  <div className="mt-2 text-xl font-semibold text-danger">{progress.failed}</div>
                </div>
                <div className="rounded-lg border bg-background/70 p-3">
                  <div className="text-xs text-muted-foreground">Run Count</div>
                  <div className="mt-2 text-xl font-semibold">{summaryQuery.data?.run_count || 0}</div>
                </div>
              </div>

              <div className="mt-4">
                <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                  <FlaskConical className="h-4 w-4 text-primary" />
                  agent ranking
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {topAgents.length === 0 ? (
                    <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">暂无 ranking 数据。</div>
                  ) : (
                    topAgents.map((agent) => (
                      <div key={agent.agent_id} className="rounded-lg border p-3">
                        <div className="font-[family-name:var(--font-mono)] text-xs">{agent.agent_id}</div>
                        <div className="mt-1 flex items-center justify-between text-sm">
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
              <CardTitle className="text-base">L2 运行矩阵</CardTitle>
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

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base">L3 任务级监控</CardTitle>
                    <CardDescription>状态 / 阶段耗时 / 失败定位</CardDescription>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => snapshotQuery.refetch()}>
                    <RefreshCw className="mr-1 h-3.5 w-3.5" />
                    刷新
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div ref={taskContainerRef} className="h-[320px] overflow-auto rounded-md border">
                  <div style={{ height: `${taskVirtualizer.getTotalSize()}px`, position: "relative" }}>
                    {taskVirtualizer.getVirtualItems().map((item) => {
                      const row = taskRows[item.index] || {};
                      const taskId = String(row.task_id || "-");
                      const agentId = String(row.agent_id || "-");
                      const variantId = String(row.variant_id || "default");
                      const sampleId = row.sample_id == null ? "-" : String(row.sample_id);
                      const status = String(row.status || "queued");
                      const durationMs = Number(row.duration_ms || 0);
                      const localTrialKey = makeTrialKey({
                        task_id: taskId,
                        agent_id: agentId,
                        variant_id: variantId,
                        sample_id: sampleId,
                      });

                      return (
                        <div
                          key={`${localTrialKey}-${item.index}`}
                          className="absolute left-0 top-0 w-full border-b px-3 py-2"
                          style={{ transform: `translateY(${item.start}px)` }}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div>
                              <div className="font-[family-name:var(--font-mono)] text-xs">{localTrialKey}</div>
                              <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                                <span>status={status}</span>
                                <span>duration={durationMs}ms</span>
                              </div>
                            </div>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setDrawerTrialKey(localTrialKey);
                                setTrialKeyInput(localTrialKey);
                                setDrawerOpen(true);
                              }}
                            >
                              查看 Pretask
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Live Runtime Events</CardTitle>
                <CardDescription>L4 日志诊断入口（支持断线续传）</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <VirtualLogViewer events={events} />
                <div className="flex items-center gap-2">
                  <Input
                    value={trialKeyInput}
                    onChange={(e) => setTrialKeyInput(e.target.value)}
                    placeholder="task::agent::variant::sample"
                    className="font-[family-name:var(--font-mono)] text-xs"
                  />
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
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Run Snapshot</CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground">
              <div className="grid gap-2 md:grid-cols-3">
                <div className="rounded border p-2">
                  <div className="mb-1 flex items-center gap-1 text-foreground">
                    <Activity className="h-3.5 w-3.5" />
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
                    <AlertTriangle className="h-3.5 w-3.5" />
                    更新时间
                  </div>
                  <div>{formatDateTime(snapshotQuery.data?.updated_at_ms)}</div>
                </div>
              </div>
            </CardContent>
          </Card>
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
