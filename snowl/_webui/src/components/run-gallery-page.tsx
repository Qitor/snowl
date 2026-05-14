"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, FolderKanban, Radar, Rows3, Sparkles, TimerReset, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { RunRow } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

type HealthResponse = {
  ok: boolean;
  project_dir: string;
};

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status}): ${url}`);
  }
  return (await response.json()) as T;
}

function summarizeModels(models: string[], variantCount: number): string {
  if (models.length === 0) {
    return `${variantCount} variants`;
  }
  if (models.length <= 2) {
    return models.join(" · ");
  }
  return `${models.slice(0, 2).join(" · ")} +${models.length - 2}`;
}

export function RunGalleryPage() {
  const [benchmarkFilter, setBenchmarkFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "running" | "completed" | "failed">("running");
  const [statusTouched, setStatusTouched] = useState(false);

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => fetchJson<HealthResponse>("/api/health"),
    refetchInterval: 5_000,
  });

  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: () => fetchJson<{ items: RunRow[] }>("/api/runs"),
    refetchInterval: 2_000,
  });

  const runs = runsQuery.data?.items || [];
  const monitorProject = healthQuery.data?.project_dir || "(project unavailable)";

  const benchmarkTabs = useMemo(() => {
    const values = Array.from(new Set(runs.map((row) => row.benchmark || "custom"))).sort();
    return ["all", ...values];
  }, [runs]);

  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      if (benchmarkFilter !== "all" && run.benchmark !== benchmarkFilter) {
        return false;
      }
      if (statusFilter === "running" && run.status !== "running") {
        return false;
      }
      if (statusFilter === "completed" && !(run.status === "completed" && run.attention_count === 0)) {
        return false;
      }
      if (statusFilter === "failed" && run.attention_count <= 0 && run.status !== "cancelled" && run.status !== "zombie") {
        return false;
      }
      return true;
    });
  }, [runs, benchmarkFilter, statusFilter]);

  const runningCount = runs.filter((row) => row.status === "running").length;
  const completedCount = runs.filter((row) => row.status === "completed" && row.attention_count === 0).length;
  const failedCount = runs.filter((row) => row.attention_count > 0 || row.status === "cancelled" || row.status === "zombie").length;
  const benchmarkCount = Math.max(benchmarkTabs.length - 1, 0);
  const continueWatching = runs.find((row) => row.status === "running") || runs.find((row) => row.attention_count > 0) || runs[0] || null;

  useEffect(() => {
    if (statusTouched || runs.length === 0) {
      return;
    }
    const hasRunning = runs.some((row) => row.status === "running");
    const hasAttention = runs.some((row) => row.attention_count > 0 || row.status === "cancelled" || row.status === "zombie");
    const hasCompleted = runs.some((row) => row.status === "completed" && row.attention_count === 0);
    if (statusFilter === "running" && !hasRunning) {
      setStatusFilter(hasAttention ? "failed" : hasCompleted ? "completed" : "all");
      return;
    }
    if (statusFilter === "failed" && !hasAttention) {
      setStatusFilter(hasCompleted ? "completed" : "all");
      return;
    }
    if (statusFilter === "completed" && !hasCompleted) {
      setStatusFilter(hasRunning ? "running" : hasAttention ? "failed" : "all");
    }
  }, [runs, statusFilter, statusTouched]);

  const topStats = [
    {
      label: "Running Now",
      value: runningCount,
      hint: "Runs currently executing",
      icon: TimerReset,
      tone: "text-amber-700",

    },
    {
      label: "Recent Complete",
      value: completedCount,
      hint: "Successfully completed runs",
      icon: CheckCircle2,
      tone: "text-emerald-700",

    },
    {
      label: "Needs Attention",
      value: failedCount,
      hint: "Runs with errors or failures",
      icon: TriangleAlert,
      tone: "text-rose-700",

    },
    {
      label: "Benchmarks",
      value: benchmarkCount,
      hint: "Benchmark types in this project",
      icon: FolderKanban,
      tone: "text-cyan-800",

    },
  ];

  return (
    <main className="mx-auto max-w-[1880px] px-5 py-6 md:px-10 md:py-8">
      <header className="mb-6 rounded-[12px] border border-[#dfdfdf] bg-white p-7 md:p-9">
        <div className="flex flex-col gap-8">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-5xl space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-muted/30 px-4 py-2 text-sm font-medium text-primary">
                <Sparkles className="h-4 w-4" />
                Run Gallery
              </div>
              <div>
                <h1 className="text-5xl font-semibold tracking-[-0.04em] md:text-7xl">Snowl Experiment Board</h1>
                <p className="mt-3 max-w-4xl text-lg leading-8 text-muted-foreground md:text-xl">
                  Select a run to view model results, task status, and live logs.
                </p>
              </div>
              <div className="rounded-lg border border-[#ededed] bg-white px-4 py-3 font-[family-name:var(--font-mono)] text-sm text-muted-foreground break-all md:text-base">
                project={monitorProject}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant={healthQuery.data?.ok ? "success" : "warning"} className="px-4 py-2 text-sm md:text-base">
                {healthQuery.data?.ok ? "monitor connected" : "monitor reconnecting"}
              </Badge>
              <Link href="/compare" className={cn(buttonVariants({ variant: "outline" }), "h-12 rounded-[6px] px-5 text-base") }>
                Compare
              </Link>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {topStats.map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.label}
                  className="rounded-[12px] border border-[#ededed] bg-white p-5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">{item.label}</div>
                      <div className={cn("mt-3 text-4xl font-semibold tracking-tight", item.tone)}>{item.value}</div>
                    </div>
                    <div className="rounded-lg bg-muted/30 p-3">
                      <Icon className={cn("h-5 w-5", item.tone)} />
                    </div>
                  </div>
                  <div className="mt-3 text-sm leading-6 text-muted-foreground">{item.hint}</div>
                </div>
              );
            })}
          </div>
        </div>
      </header>

      <section className="space-y-5">
        {continueWatching ? (
          <Card className="rounded-[12px] border border-[#dfdfdf] bg-white">
            <CardHeader className="gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <CardTitle className="text-3xl tracking-tight">Continue Watching</CardTitle>
                <CardDescription className="mt-2 text-base leading-7">
                  Tracks your last viewed or attention-needed run for quick access.
                </CardDescription>
              </div>
              <Link href={`/runs/${encodeURIComponent(String(continueWatching.run_id))}`} className={cn(buttonVariants({ variant: "default" }), "h-12 rounded-[6px] px-5 text-base")}>
                Open run
              </Link>
            </CardHeader>
            <CardContent className="grid gap-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
              <div className="rounded-[12px] border border-[#ededed] bg-white p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{continueWatching.benchmark}</Badge>
                  <Badge
                    variant={
                      continueWatching.status === "running"
                        ? "warning"
                        : continueWatching.status === "cancelled" || continueWatching.status === "zombie" || continueWatching.attention_count > 0
                          ? "danger"
                          : "success"
                    }
                  >
                    {continueWatching.status === "running"
                      ? "running"
                      : continueWatching.status === "cancelled"
                        ? "cancelled"
                        : continueWatching.status === "zombie"
                          ? "zombie"
                        : continueWatching.attention_count > 0
                          ? "needs attention"
                          : "completed"}
                  </Badge>
                  {continueWatching.stalled ? <Badge variant="danger">stalled</Badge> : null}
                  {continueWatching.heartbeat_only ? <Badge variant="warning">heartbeat only</Badge> : null}
                  {continueWatching.observer_stale ? <Badge variant="warning">observer stale</Badge> : null}
                  {continueWatching.status === "running" && continueWatching.runner_alive ? <Badge variant="outline">runner alive</Badge> : null}
                </div>
                <div className="mt-4 font-[family-name:var(--font-mono)] text-xl font-semibold break-all">{continueWatching.run_id}</div>
                <div className="mt-2 text-base text-muted-foreground">updated {formatDateTime(continueWatching.updated_at_ms)}</div>
                <div className="mt-5 grid gap-3 sm:grid-cols-4">
                  <div className="rounded-[8px] border border-[#ededed] bg-white p-3">
                    <div className="text-sm text-muted-foreground">Progress</div>
                    <div className="mt-2 text-2xl font-semibold">{continueWatching.done}/{continueWatching.total}</div>
                  </div>
                  <div className="rounded-[8px] border border-[#ededed] bg-white p-3">
                    <div className="text-sm text-muted-foreground">Variants</div>
                    <div className="mt-2 text-2xl font-semibold">{continueWatching.variant_count}</div>
                  </div>
                  <div className="rounded-[8px] border border-[#ededed] bg-white p-3">
                    <div className="text-sm text-muted-foreground">Attention</div>
                    <div className={cn("mt-2 text-2xl font-semibold", continueWatching.attention_count > 0 ? "text-danger" : "text-success")}>
                      {continueWatching.attention_count}
                    </div>
                  </div>
                  <div className="rounded-[8px] border border-[#ededed] bg-white p-3">
                    <div className="text-sm text-muted-foreground">Task monitor</div>
                    <div className="mt-2 text-2xl font-semibold">{continueWatching.has_task_monitor ? "ready" : "waiting"}</div>
                  </div>
                </div>
              </div>
              <div className="rounded-[12px] border border-[#ededed] bg-white p-5">
                <div className="text-sm font-medium uppercase tracking-[0.16em] text-muted-foreground">Operator signals</div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {continueWatching.is_live ? <Badge variant="warning">live observer attached</Badge> : <Badge variant="outline">archived run</Badge>}
                  {continueWatching.attention_count > 0 ? <Badge variant="danger">{continueWatching.attention_count} signals need review</Badge> : <Badge variant="success">no active attention signals</Badge>}
                  {!continueWatching.has_task_monitor ? <Badge variant="warning">task monitor missing</Badge> : null}
                  {continueWatching.stalled ? <Badge variant="danger">no recent progress</Badge> : null}
                  {continueWatching.observer_stale ? <Badge variant="warning">observer lagging behind runner</Badge> : null}
                </div>
                <div className="mt-5 text-base leading-7 text-muted-foreground">
                  {continueWatching.attention_count > 0
                    ? "This run needs attention. Check Tasks to diagnose bottlenecks."
                    : "Your latest run. Check task progress first, then switch to logs if needed."}
                </div>
              </div>
            </CardContent>
          </Card>
        ) : null}

        <Card className="rounded-[12px] border border-[#dfdfdf] bg-white">
          <CardHeader className="gap-4 pb-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle className="text-3xl tracking-tight">Run Gallery</CardTitle>
                <CardDescription className="mt-2 text-base leading-7">
                  Filter by benchmark and status to find a specific run.
                </CardDescription>
              </div>
              <div className="inline-flex flex-wrap gap-2 rounded-[6px] border border-[#dfdfdf] bg-muted/30 p-1.5">
                {([
                  { key: "running", label: "Running" },
                  { key: "failed", label: "Needs attention" },
                  { key: "completed", label: "Completed" },
                  { key: "all", label: "All" },
                ] as const).map((status) => {
                  const active = statusFilter === status.key;
                  return (
                    <button
                    key={status.key}
                    type="button"
                    onClick={() => {
                      setStatusTouched(true);
                      setStatusFilter(status.key);
                    }}
                    className={cn(
                        "rounded-[4px] px-4 py-2.5 text-sm font-medium transition md:text-base",
                        active
                          ? "bg-foreground text-background shadow-sm"
                          : "text-muted-foreground hover:bg-white hover:text-foreground",
                      )}
                    >
                      {status.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {benchmarkTabs.map((benchmark) => {
                const active = benchmarkFilter === benchmark;
                const label = benchmark === "all" ? "All benchmarks" : benchmark;
                const count = runs.filter((row) => benchmark === "all" || row.benchmark === benchmark).length;
                return (
                  <button
                    key={benchmark}
                    type="button"
                    onClick={() => setBenchmarkFilter(benchmark)}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-[6px] border px-4 py-2.5 text-sm font-medium transition md:text-base",
                      active
                        ? "border-primary/40 bg-primary text-primary-foreground shadow-sm"
                        : "bg-background hover:bg-muted/70",
                    )}
                  >
                    <Rows3 className="h-4 w-4" />
                    {label}
                    <span className={cn("rounded-full px-2 py-0.5 text-xs", active ? "bg-primary-foreground/20" : "bg-muted text-muted-foreground")}>
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          </CardHeader>
        </Card>

        {filteredRuns.length === 0 ? (
          <Card className="rounded-[12px] border border-dashed border-primary/30 bg-white">
            <CardHeader>
              <CardTitle className="text-3xl">No runs match your filters</CardTitle>
              <CardDescription className="text-base leading-7">
                Try changing the benchmark tab or status filter. Monitor directory: `{monitorProject}/.snowl/runs`。
              </CardDescription>
            </CardHeader>
          </Card>
        ) : (
          <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-3">
            {filteredRuns.map((run) => {
              const progress = run.total > 0 ? run.done / run.total : 0;
              const needsAttention = run.attention_count > 0;
              const recoverable = Number(run.recoverable_trials || 0);
              const recovered = Number(run.recovered_trials || 0);
              const stillFailing = Number(run.still_failing_trials || 0);
              return (
                <Link key={run.run_id} href={`/runs/${encodeURIComponent(run.run_id)}`} className="group block">
                  <Card className="h-full overflow-hidden rounded-[12px] border border-[#dfdfdf] bg-white transition duration-200 group-hover:-translate-y-0.5 group-hover:shadow-md">
                    <CardHeader className="gap-4 pb-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="space-y-3">
                          <div className="flex flex-wrap gap-2">
                            <Badge variant="outline" className="bg-white text-sm">{run.benchmark}</Badge>
                            <Badge
                              variant={run.status === "running" ? "warning" : run.status === "cancelled" || run.status === "zombie" || needsAttention ? "danger" : "success"}
                              className="text-sm"
                            >
                              {run.status === "running"
                                ? "running"
                                : run.status === "cancelled"
                                  ? "cancelled"
                                  : run.status === "zombie"
                                    ? "zombie"
                                  : needsAttention
                                    ? "needs attention"
                                    : "completed"}
                            </Badge>
                            {run.is_live ? <Badge variant="warning" className="text-sm">live</Badge> : null}
                            {run.stalled ? <Badge variant="danger" className="text-sm">stalled</Badge> : null}
                            {run.observer_stale ? <Badge variant="warning" className="text-sm">observer stale</Badge> : null}
                          </div>
                          <div>
                            <CardTitle className="font-[family-name:var(--font-mono)] text-xl leading-8 break-all">{run.run_id}</CardTitle>
                            <CardDescription className="mt-2 text-sm md:text-base">
                              updated {formatDateTime(run.updated_at_ms)}{run.experiment_id ? ` · ${run.experiment_id}` : ""}
                            </CardDescription>
                          </div>
                        </div>
                        <div className="rounded-[8px] border border-[#ededed] bg-white p-3 text-right">
                          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Progress</div>
                          <div className="mt-2 text-3xl font-semibold tracking-tight">{Math.round(progress * 100)}%</div>
                        </div>
                      </div>
                    </CardHeader>

                    <CardContent className="space-y-5">
                      <div className="grid gap-3 sm:grid-cols-3">
                        <div className="rounded-[8px] border border-[#ededed] bg-white p-4">
                          <div className="text-sm text-muted-foreground">Tasks done</div>
                          <div className="mt-2 text-3xl font-semibold">{run.done}</div>
                          <div className="mt-1 text-sm text-muted-foreground">of {run.total}</div>
                        </div>
                        <div className="rounded-[8px] border border-[#ededed] bg-white p-4">
                          <div className="text-sm text-muted-foreground">Models / variants</div>
                          <div className="mt-2 text-3xl font-semibold">{run.variant_count}</div>
                          <div className="mt-1 text-sm text-muted-foreground">tracked identities</div>
                        </div>
                        <div className="rounded-[8px] border border-[#ededed] bg-white p-4">
                          <div className="text-sm text-muted-foreground">Attention</div>
                          <div className={cn("mt-2 text-3xl font-semibold", needsAttention ? "text-danger" : "text-success")}>{run.attention_count}</div>
                          <div className="mt-1 text-sm text-muted-foreground">operator signals</div>
                        </div>
                      </div>

                      <div className="grid gap-3 sm:grid-cols-3">
                        <div className="rounded-[8px] border border-[#ededed] bg-white p-4">
                          <div className="text-sm text-muted-foreground">Recoverable</div>
                          <div className={cn("mt-2 text-3xl font-semibold", recoverable > 0 ? "text-warning" : "")}>{recoverable}</div>
                          <div className="mt-1 text-sm text-muted-foreground">unfinished + non-success</div>
                        </div>
                        <div className="rounded-[8px] border border-[#ededed] bg-white p-4">
                          <div className="text-sm text-muted-foreground">Recovered</div>
                          <div className={cn("mt-2 text-3xl font-semibold", recovered > 0 ? "text-success" : "")}>{recovered}</div>
                          <div className="mt-1 text-sm text-muted-foreground">latest attempt healthy</div>
                        </div>
                        <div className="rounded-[8px] border border-[#ededed] bg-white p-4">
                          <div className="text-sm text-muted-foreground">Still failing</div>
                          <div className={cn("mt-2 text-3xl font-semibold", stillFailing > 0 ? "text-danger" : "")}>{stillFailing}</div>
                          <div className="mt-1 text-sm text-muted-foreground">retried but unresolved</div>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-sm text-muted-foreground md:text-base">
                          <span>Execution</span>
                          <span>{run.done}/{run.total}</span>
                        </div>
                        <div className="h-3.5 rounded-full bg-muted/80">
                          <div
                            className={cn(
                              "h-3.5 rounded-full transition-all",
                              run.status === "running" ? "bg-amber-500" : run.status === "cancelled" || run.status === "zombie" || needsAttention ? "bg-rose-500" : "bg-primary",
                            )}
                            style={{ width: `${Math.max(progress > 0 ? 8 : 0, progress * 100)}%` }}
                          />
                        </div>
                      </div>

                      <div className="rounded-[8px] border border-[#ededed] bg-white p-4">
                        <div className="mb-2 flex items-center gap-2 text-sm font-medium uppercase tracking-[0.16em] text-muted-foreground">
                          <Radar className="h-4 w-4" />
                          Model summary
                        </div>
                        <div className="text-base leading-7 text-foreground md:text-lg">{summarizeModels(run.models, run.variant_count)}</div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Badge variant="outline">{run.models.length || run.variant_count} models</Badge>
                          {run.is_live ? <Badge variant="warning">live observer</Badge> : <Badge variant="outline">archived run</Badge>}
                          <Badge variant={needsAttention ? "danger" : "success"}>{needsAttention ? "needs review" : "healthy"}</Badge>
                          {recoverable > 0 ? <Badge variant="warning">{recoverable} recoverable</Badge> : null}
                          {recovered > 0 ? <Badge variant="success">{recovered} recovered</Badge> : null}
                          {stillFailing > 0 ? <Badge variant="danger">{stillFailing} still failing</Badge> : null}
                          {!run.has_task_monitor ? <Badge variant="warning">task monitor missing</Badge> : null}
                          {run.heartbeat_only ? <Badge variant="warning">heartbeat only</Badge> : null}
                          {run.status === "running" && run.runner_alive ? <Badge variant="outline">runner alive</Badge> : null}
                        </div>
                      </div>

                      <div className="rounded-[8px] border border-dashed border-primary/25 bg-primary/5 px-4 py-3 text-sm leading-6 text-muted-foreground">
                          {run.status === "running"
                            ? run.observer_stale
                              ? "The runner still appears alive, but the observer is lagging behind the latest runtime heartbeat."
                              : run.stalled
                                ? "Run is alive but no meaningful progress has been observed recently."
                                : "Run is actively progressing; enter workspace to watch task-level movement."
                            : run.status === "cancelled"
                              ? "This run was explicitly interrupted before writing a final summary."
                              : run.status === "zombie"
                                ? "This looks like a stale historical run: the runner is gone, but the run never wrote a terminal summary."
                                : needsAttention
                                  ? "This run completed with signals that still need review."
                                  : "This run completed cleanly and is ready for result review."}
                      </div>

                      <div className="flex items-center justify-between rounded-[8px] border border-dashed border-primary/25 bg-primary/5 px-4 py-3 text-base font-medium text-primary transition group-hover:border-primary/45 group-hover:bg-primary/10">
                        <span>{run.status === "running" ? "Watch run" : "Open workspace"}</span>
                        <ArrowRight className="h-5 w-5 transition group-hover:translate-x-0.5" />
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
