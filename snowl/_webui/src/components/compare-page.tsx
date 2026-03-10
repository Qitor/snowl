"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FlaskConical } from "lucide-react";

import { MatrixHeatmap } from "@/components/matrix-heatmap";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import type { ExperimentRow, ExperimentSummaryResponse } from "@/lib/types";
import { cn, formatDateTime, formatPercent } from "@/lib/utils";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status}): ${url}`);
  }
  return (await response.json()) as T;
}

export function ComparePage() {
  const [selectedExperiment, setSelectedExperiment] = useState("");
  const [view, setView] = useState<"variant-first" | "benchmark-first">("variant-first");

  const experimentsQuery = useQuery({
    queryKey: ["experiments"],
    queryFn: () => fetchJson<{ items: ExperimentRow[] }>("/api/experiments"),
    refetchInterval: 5_000,
  });

  const experiments = experimentsQuery.data?.items || [];

  useEffect(() => {
    if (!selectedExperiment && experiments.length > 0) {
      setSelectedExperiment(experiments[0].experiment_id);
    }
  }, [experiments, selectedExperiment]);

  const summaryQuery = useQuery({
    queryKey: ["experiment-summary", selectedExperiment, view],
    queryFn: () =>
      fetchJson<ExperimentSummaryResponse>(
        `/api/experiments/${encodeURIComponent(selectedExperiment)}/summary?view=${encodeURIComponent(view)}`,
      ),
    enabled: Boolean(selectedExperiment),
    refetchInterval: 4_000,
  });

  const summary = summaryQuery.data;
  const topAgents = summary?.agents.slice(0, 8) || [];
  const completionRate = summary?.global_progress.total
    ? summary.global_progress.done / summary.global_progress.total
    : 0;

  return (
    <main className="mx-auto max-w-[1880px] px-5 py-6 md:px-10 md:py-8">
      <header className="mb-6 rounded-[28px] border bg-gradient-to-r from-emerald-50/95 via-cyan-50/95 to-sky-100/90 p-7 shadow">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <Link href="/" className={cn(buttonVariants({ variant: "outline" }), "h-11 px-4")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回 Runs
            </Link>
            <div>
              <h1 className="text-4xl font-semibold tracking-tight md:text-5xl">Historical Compare</h1>
              <p className="mt-2 text-xl text-muted-foreground">这里专门用来看 experiment / 多次 run 的历史对比，不打断主流程。</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-base text-muted-foreground">Perspective</label>
            <Select
              value={view}
              onChange={(e) => setView((e.target.value as "variant-first" | "benchmark-first") || "variant-first")}
              className="w-[180px]"
            >
              <option value="variant-first">By model</option>
              <option value="benchmark-first">By benchmark</option>
            </Select>
          </div>
        </div>
      </header>

      <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="text-2xl">Experiments</CardTitle>
            <CardDescription>选择一个 experiment，查看它里面多次 runs 的整体表现。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="max-h-[720px] space-y-2 overflow-auto pr-1">
              {experiments.map((row) => {
                const active = row.experiment_id === selectedExperiment;
                return (
                  <button
                    key={row.experiment_id}
                    className={cn(
                      "w-full rounded-2xl border p-4 text-left transition",
                      active ? "border-primary bg-primary/10" : "hover:bg-muted/70",
                    )}
                    onClick={() => setSelectedExperiment(row.experiment_id)}
                  >
                    <div className="font-[family-name:var(--font-mono)] text-sm break-all">{row.experiment_id}</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Badge variant="outline">runs {row.run_count}</Badge>
                      <Badge variant="warning">running {row.running}</Badge>
                      <Badge variant="success">done {row.completed}</Badge>
                    </div>
                    <div className="mt-2 text-sm text-muted-foreground">{formatDateTime(row.updated_at_ms)}</div>
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <section className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-2xl">Experiment Summary</CardTitle>
              <CardDescription>{selectedExperiment || "请选择一个 experiment"}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-5">
                <div className="rounded-2xl border bg-background/70 p-3">
                  <div className="text-base text-muted-foreground">Overall Progress</div>
                  <div className="mt-2 text-3xl font-semibold">{formatPercent(completionRate)}</div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    {summary?.global_progress.done || 0}/{summary?.global_progress.total || 0}
                  </div>
                </div>
                <div className="rounded-2xl border bg-background/70 p-3">
                  <div className="text-base text-muted-foreground">Running</div>
                  <div className="mt-2 text-3xl font-semibold text-warning">{summary?.global_progress.running || 0}</div>
                </div>
                <div className="rounded-2xl border bg-background/70 p-3">
                  <div className="text-base text-muted-foreground">Completed</div>
                  <div className="mt-2 text-3xl font-semibold text-success">{summary?.global_progress.completed || 0}</div>
                </div>
                <div className="rounded-2xl border bg-background/70 p-3">
                  <div className="text-base text-muted-foreground">Failed</div>
                  <div className="mt-2 text-3xl font-semibold text-danger">{summary?.global_progress.failed || 0}</div>
                </div>
                <div className="rounded-2xl border bg-background/70 p-3">
                  <div className="text-base text-muted-foreground">Run Count</div>
                  <div className="mt-2 text-3xl font-semibold">{summary?.run_count || 0}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <FlaskConical className="h-4 w-4 text-primary" />
                <CardTitle className="text-2xl">Model Ranking</CardTitle>
              </div>
              <CardDescription>按 variant / model 聚合 experiment 内的历史表现。</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-2 md:grid-cols-2">
              {topAgents.length === 0 ? (
                <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">暂无 ranking 数据。</div>
              ) : (
                topAgents.map((agent) => (
                  <div key={`${agent.display_id}-${agent.model || "-"}`} className="rounded-2xl border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-[family-name:var(--font-mono)] text-base break-all">{agent.display_id}</div>
                      {agent.model ? <Badge variant="outline">{agent.model}</Badge> : null}
                    </div>
                    <div className="mt-2 flex items-center justify-between text-base">
                      <span className="text-muted-foreground">rank score</span>
                      <span className="font-semibold">{agent.rank_score.toFixed(4)}</span>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-2xl">Compare Matrix</CardTitle>
              <CardDescription>查看这个 experiment 里不同 benchmark 或不同模型的聚合对比。</CardDescription>
            </CardHeader>
            <CardContent>
              <MatrixHeatmap
                matrix={summary?.matrix || {}}
                rowLabel={view === "variant-first" ? "Variant / Model" : "Benchmark"}
                colLabel={view === "variant-first" ? "Benchmark" : "Variant / Model"}
              />
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
