"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
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
  const [statusFilter, setStatusFilter] = useState<"all" | "running" | "completed" | "failed">("all");

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
      if (statusFilter === "completed" && !(run.status === "completed" && run.failed === 0)) {
        return false;
      }
      if (statusFilter === "failed" && run.failed <= 0) {
        return false;
      }
      return true;
    });
  }, [runs, benchmarkFilter, statusFilter]);

  const runningCount = runs.filter((row) => row.status === "running").length;
  const completedCount = runs.filter((row) => row.status === "completed" && row.failed === 0).length;
  const failedCount = runs.filter((row) => row.failed > 0).length;
  const benchmarkCount = Math.max(benchmarkTabs.length - 1, 0);

  const topStats = [
    {
      label: "Running Now",
      value: runningCount,
      hint: "当前仍在进行中的评测",
      icon: TimerReset,
      tone: "text-amber-700",
      bg: "from-amber-50 to-orange-50",
    },
    {
      label: "Recent Complete",
      value: completedCount,
      hint: "已顺利完成的 runs",
      icon: CheckCircle2,
      tone: "text-emerald-700",
      bg: "from-emerald-50 to-lime-50",
    },
    {
      label: "Needs Attention",
      value: failedCount,
      hint: "包含错误或失败 trial",
      icon: TriangleAlert,
      tone: "text-rose-700",
      bg: "from-rose-50 to-orange-50",
    },
    {
      label: "Benchmarks",
      value: benchmarkCount,
      hint: "当前项目下的 benchmark 种类",
      icon: FolderKanban,
      tone: "text-cyan-800",
      bg: "from-cyan-50 to-sky-50",
    },
  ];

  return (
    <main className="mx-auto max-w-[1880px] px-5 py-6 md:px-10 md:py-8">
      <header className="mb-6 overflow-hidden rounded-[34px] border border-white/70 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.18),transparent_32%),radial-gradient(circle_at_top_right,rgba(6,182,212,0.18),transparent_28%),linear-gradient(160deg,rgba(248,255,252,0.98),rgba(239,250,255,0.95))] p-7 shadow-[0_24px_80px_rgba(15,118,110,0.12)] md:p-9">
        <div className="flex flex-col gap-8">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-5xl space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-white/80 px-4 py-2 text-sm font-medium text-primary shadow-sm">
                <Sparkles className="h-4 w-4" />
                Run Gallery
              </div>
              <div>
                <h1 className="text-5xl font-semibold tracking-[-0.04em] md:text-7xl">Snowl Experiment Board</h1>
                <p className="mt-3 max-w-4xl text-lg leading-8 text-muted-foreground md:text-xl">
                  先挑中这一次评测运行，再进入对应 workspace 看多模型结果、任务状态和实时日志。
                </p>
              </div>
              <div className="rounded-2xl border border-white/80 bg-white/70 px-4 py-3 font-[family-name:var(--font-mono)] text-sm text-muted-foreground shadow-sm break-all md:text-base">
                project={monitorProject}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant={healthQuery.data?.ok ? "success" : "warning"} className="px-4 py-2 text-sm md:text-base">
                {healthQuery.data?.ok ? "monitor connected" : "monitor reconnecting"}
              </Badge>
              <Link href="/compare" className={cn(buttonVariants({ variant: "outline" }), "h-12 rounded-full px-5 text-base") }>
                历史对比
              </Link>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {topStats.map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.label}
                  className={cn(
                    "rounded-[24px] border border-white/80 bg-gradient-to-br p-5 shadow-sm",
                    item.bg,
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">{item.label}</div>
                      <div className={cn("mt-3 text-4xl font-semibold tracking-tight", item.tone)}>{item.value}</div>
                    </div>
                    <div className="rounded-2xl bg-white/80 p-3 shadow-sm">
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
        <Card className="rounded-[30px] border-white/80 bg-white/88 shadow-[0_18px_60px_rgba(15,23,42,0.06)] backdrop-blur-sm">
          <CardHeader className="gap-4 pb-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle className="text-3xl tracking-tight">Run Gallery</CardTitle>
                <CardDescription className="mt-2 text-base leading-7">
                  用 benchmark tabs 先收窄范围，再按状态过滤，快速锁定你想看的那次运行。
                </CardDescription>
              </div>
              <div className="inline-flex flex-wrap gap-2 rounded-full border bg-muted/35 p-1.5">
                {([
                  { key: "all", label: "All" },
                  { key: "running", label: "Running" },
                  { key: "completed", label: "Completed" },
                  { key: "failed", label: "Failed" },
                ] as const).map((status) => {
                  const active = statusFilter === status.key;
                  return (
                    <button
                      key={status.key}
                      type="button"
                      onClick={() => setStatusFilter(status.key)}
                      className={cn(
                        "rounded-full px-4 py-2.5 text-sm font-medium transition md:text-base",
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
                      "inline-flex items-center gap-2 rounded-full border px-4 py-2.5 text-sm font-medium transition md:text-base",
                      active
                        ? "border-primary/40 bg-primary text-primary-foreground shadow-sm"
                        : "bg-background hover:bg-muted/70",
                    )}
                  >
                    <Rows3 className="h-4 w-4" />
                    {label}
                    <span className={cn("rounded-full px-2 py-0.5 text-xs", active ? "bg-white/20" : "bg-muted text-muted-foreground")}>
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          </CardHeader>
        </Card>

        {filteredRuns.length === 0 ? (
          <Card className="rounded-[28px] border-dashed border-primary/30 bg-white/80">
            <CardHeader>
              <CardTitle className="text-3xl">暂无符合条件的 runs</CardTitle>
              <CardDescription className="text-base leading-7">
                试试切换 benchmark tabs 或状态筛选。监控目录仍然是 `{monitorProject}/.snowl/runs`。
              </CardDescription>
            </CardHeader>
          </Card>
        ) : (
          <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-3">
            {filteredRuns.map((run) => {
              const progress = run.total > 0 ? run.done / run.total : 0;
              const isFailed = run.failed > 0;
              return (
                <Link key={run.run_id} href={`/runs/${encodeURIComponent(run.run_id)}`} className="group block">
                  <Card className="h-full overflow-hidden rounded-[30px] border-white/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(249,255,253,0.96))] shadow-[0_16px_60px_rgba(15,23,42,0.06)] transition duration-200 group-hover:-translate-y-1.5 group-hover:shadow-[0_24px_80px_rgba(13,148,136,0.14)]">
                    <CardHeader className="gap-4 pb-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="space-y-3">
                          <div className="flex flex-wrap gap-2">
                            <Badge variant="outline" className="bg-white/80 text-sm">{run.benchmark}</Badge>
                            <Badge variant={run.status === "running" ? "warning" : isFailed ? "danger" : "success"} className="text-sm">
                              {run.status === "running" ? "running" : isFailed ? "completed with failures" : "completed"}
                            </Badge>
                            {run.is_live ? <Badge variant="warning" className="text-sm">live</Badge> : null}
                          </div>
                          <div>
                            <CardTitle className="font-[family-name:var(--font-mono)] text-xl leading-8 break-all">{run.run_id}</CardTitle>
                            <CardDescription className="mt-2 text-sm md:text-base">updated {formatDateTime(run.updated_at_ms)}</CardDescription>
                          </div>
                        </div>
                        <div className="rounded-2xl border bg-muted/40 p-3 text-right shadow-inner">
                          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Progress</div>
                          <div className="mt-2 text-3xl font-semibold tracking-tight">{Math.round(progress * 100)}%</div>
                        </div>
                      </div>
                    </CardHeader>

                    <CardContent className="space-y-5">
                      <div className="grid gap-3 sm:grid-cols-3">
                        <div className="rounded-[22px] border bg-muted/25 p-4">
                          <div className="text-sm text-muted-foreground">Tasks done</div>
                          <div className="mt-2 text-3xl font-semibold">{run.done}</div>
                          <div className="mt-1 text-sm text-muted-foreground">of {run.total}</div>
                        </div>
                        <div className="rounded-[22px] border bg-muted/25 p-4">
                          <div className="text-sm text-muted-foreground">Models / variants</div>
                          <div className="mt-2 text-3xl font-semibold">{run.variant_count}</div>
                          <div className="mt-1 text-sm text-muted-foreground">tracked identities</div>
                        </div>
                        <div className="rounded-[22px] border bg-muted/25 p-4">
                          <div className="text-sm text-muted-foreground">Failures</div>
                          <div className={cn("mt-2 text-3xl font-semibold", isFailed ? "text-danger" : "text-success")}>{run.failed}</div>
                          <div className="mt-1 text-sm text-muted-foreground">task-level errors</div>
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
                              run.status === "running" ? "bg-amber-500" : isFailed ? "bg-rose-500" : "bg-primary",
                            )}
                            style={{ width: `${Math.max(progress > 0 ? 8 : 0, progress * 100)}%` }}
                          />
                        </div>
                      </div>

                      <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(240,253,250,0.9),rgba(255,255,255,0.85))] p-4">
                        <div className="mb-2 flex items-center gap-2 text-sm font-medium uppercase tracking-[0.16em] text-muted-foreground">
                          <Radar className="h-4 w-4" />
                          Model summary
                        </div>
                        <div className="text-base leading-7 text-foreground md:text-lg">{summarizeModels(run.models, run.variant_count)}</div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Badge variant="outline">{run.models.length || run.variant_count} models</Badge>
                          {run.is_live ? <Badge variant="warning">live observer</Badge> : <Badge variant="outline">archived run</Badge>}
                          <Badge variant={isFailed ? "danger" : "success"}>{isFailed ? "needs review" : "healthy"}</Badge>
                        </div>
                      </div>

                      <div className="flex items-center justify-between rounded-[22px] border border-dashed border-primary/25 bg-primary/5 px-4 py-3 text-base font-medium text-primary transition group-hover:border-primary/45 group-hover:bg-primary/10">
                        <span>Open workspace</span>
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
