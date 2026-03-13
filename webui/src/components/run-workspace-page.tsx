"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Activity, ArrowLeft, CalendarClock, FlaskConical, RefreshCw } from "lucide-react";

import { MatrixBarChart } from "@/components/matrix-bar-chart";
import { PretaskDrawer } from "@/components/pretask-drawer";
import { TrialDetailPanel } from "@/components/trial-detail-panel";
import { TrialQuickPeekDrawer } from "@/components/trial-quick-peek-drawer";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { VirtualLogViewer } from "@/components/virtual-log-viewer";
import type { RunSnapshot, RunSummaryResponse, RuntimeEvent } from "@/lib/types";
import {
  cn,
  formatDateTime,
  formatPercent,
  makeDisplayId,
  makeIdentityKey,
  makeTrialKey,
  truncateMiddle,
} from "@/lib/utils";

type IdentityOption = {
  display_id: string;
  agent_id: string;
  variant_id: string;
  model: string | null;
};

type EnrichedTaskRow = Record<string, unknown> & {
  identityKey: string;
  displayId: string;
  model: string | null;
  taskId: string;
  agentId: string;
  variantId: string;
  sampleId: string;
  status: string;
  durationMs: number;
  trialKey: string;
};

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

    return () => source.close();
  }, [runId]);

  return { events, connected };
}

export function RunWorkspacePage({ runId }: { runId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const initialTab = (() => {
    const raw = (searchParams.get("tab") || "").trim().toLowerCase();
    if (raw === "overview" || raw === "runtime" || raw === "trial_detail") {
      return raw as "overview" | "runtime" | "trial_detail";
    }
    return "tasks";
  })();
  const initialTrialKey = (searchParams.get("trial_key") || "").trim();

  const [activeTab, setActiveTab] = useState<"overview" | "tasks" | "runtime" | "trial_detail">(initialTab);
  const [view, setView] = useState<"variant-first" | "benchmark-first">("variant-first");
  const [identityFilter, setIdentityFilter] = useState("all");
  const [trialKeyInput, setTrialKeyInput] = useState(initialTrialKey);
  const [selectedTrialKey, setSelectedTrialKey] = useState(initialTrialKey);
  const [taskSearch, setTaskSearch] = useState("");
  const [taskStatusFilter, setTaskStatusFilter] = useState("all");
  const [taskAttentionOnly, setTaskAttentionOnly] = useState(false);
  const [runtimeSearch, setRuntimeSearch] = useState("");
  const [runtimeEventFilter, setRuntimeEventFilter] = useState("attention");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTrialKey, setDrawerTrialKey] = useState("");
  const [quickPeekOpen, setQuickPeekOpen] = useState(false);
  const [quickPeekTrialKey, setQuickPeekTrialKey] = useState("");
  const [retrySubmitting, setRetrySubmitting] = useState(false);
  const [retryFeedback, setRetryFeedback] = useState<string | null>(null);

  const syncWorkspaceUrl = (next: {
    tab?: "overview" | "tasks" | "runtime" | "trial_detail";
    trialKey?: string;
  }) => {
    const params = new URLSearchParams(searchParams.toString());
    const tab = next.tab ?? activeTab;
    const trialKey = typeof next.trialKey === "string" ? next.trialKey.trim() : selectedTrialKey.trim();
    if (tab === "tasks") {
      params.delete("tab");
    } else {
      params.set("tab", tab);
    }
    if (trialKey) {
      params.set("trial_key", trialKey);
    } else {
      params.delete("trial_key");
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const openWorkspaceTrialDetail = (trialKey: string) => {
    const normalized = trialKey.trim();
    if (!normalized) {
      return;
    }
    setSelectedTrialKey(normalized);
    setTrialKeyInput(normalized);
    setActiveTab("trial_detail");
    syncWorkspaceUrl({ tab: "trial_detail", trialKey: normalized });
  };

  const runSummaryQuery = useQuery({
    queryKey: ["run-summary", runId, view],
    queryFn: () => fetchJson<RunSummaryResponse>(`/api/runs/${encodeURIComponent(runId)}/summary?view=${encodeURIComponent(view)}`),
    enabled: Boolean(runId),
    refetchInterval: 2_000,
  });

  const snapshotQuery = useQuery({
    queryKey: ["snapshot", runId],
    queryFn: () => fetchJson<RunSnapshot>(`/api/runs/${encodeURIComponent(runId)}/snapshot`),
    enabled: Boolean(runId),
    refetchInterval: 2_000,
  });

  const pretaskQuery = useQuery({
    queryKey: ["pretask", runId, drawerTrialKey, drawerOpen],
    queryFn: () =>
      fetchJson<{ items: Array<Record<string, unknown>> }>(
        `/api/runs/${encodeURIComponent(runId)}/pretask?trial_key=${encodeURIComponent(drawerTrialKey)}`,
      ),
    enabled: Boolean(drawerOpen && runId && drawerTrialKey),
    refetchInterval: drawerOpen ? 2_000 : false,
  });

  const trialDetailQuery = useQuery({
    queryKey: ["trial-detail", runId, selectedTrialKey],
    queryFn: () =>
      fetchJson<Record<string, unknown>>(
        `/api/runs/${encodeURIComponent(runId)}/trial?trial_key=${encodeURIComponent(selectedTrialKey)}`,
      ),
    enabled: Boolean(runId && selectedTrialKey),
    refetchInterval: selectedTrialKey ? 2_000 : false,
  });

  const quickPeekTrialQuery = useQuery({
    queryKey: ["trial-quick-peek", runId, quickPeekTrialKey, quickPeekOpen],
    queryFn: () =>
      fetchJson<Record<string, unknown>>(
        `/api/runs/${encodeURIComponent(runId)}/trial?trial_key=${encodeURIComponent(quickPeekTrialKey)}`,
      ),
    enabled: Boolean(runId && quickPeekOpen && quickPeekTrialKey),
    refetchInterval: quickPeekOpen ? 2_000 : false,
  });

  const { events, connected } = useRuntimeStream(runId);
  const runSummary = runSummaryQuery.data;
  const runSnapshot = snapshotQuery.data;

  const identityOptions = useMemo<IdentityOption[]>(() => {
    if (Array.isArray(runSummary?.identities) && runSummary.identities.length > 0) {
      return runSummary.identities;
    }
    if (Array.isArray(runSnapshot?.identities) && runSnapshot.identities.length > 0) {
      return runSnapshot.identities;
    }
    return [];
  }, [runSummary?.identities, runSnapshot?.identities]);

  const progress = runSummary?.global_progress || {
    done: 0,
    total: 0,
    running: 0,
    completed: 0,
    failed: 0,
  };
  const completionRate = progress.total > 0 ? progress.done / progress.total : 0;
  const topIdentities = runSummary?.agents.slice(0, 8) || [];
  const selectedModels = runSummary?.models || runSnapshot?.models || [];
  const selectedVariantCount = runSummary?.variant_count || runSnapshot?.variant_count || 0;
  const plannedTrials = Number(runSnapshot?.planned_trials || runSnapshot?.plan?.trial_count || progress.total || 0);
  const plannedTaskCount = Number(runSnapshot?.planned_tasks || (Array.isArray(runSnapshot?.plan?.task_ids) ? runSnapshot?.plan?.task_ids.length : 0));
  const scoredTrials = Number(runSummary?.scored_trials || runSnapshot?.scored_trials || 0);
  const recoverableTrials = Number(runSummary?.recoverable_trials || runSnapshot?.recoverable_trials || 0);
  const retriedTrials = Number(runSummary?.retried_trials || runSnapshot?.retried_trials || runSnapshot?.retry_attempts || 0);
  const recoveredTrials = Number(runSummary?.recovered_trials || runSnapshot?.recovered_trials || runSnapshot?.recovered_count || 0);
  const stillFailingTrials = Number(runSummary?.still_failing_trials || runSnapshot?.still_failing_trials || runSnapshot?.outstanding_failures || 0);
  const unfinishedTrials = Number(runSummary?.unfinished_trials || runSnapshot?.unfinished_trials || Math.max(0, plannedTrials - progress.done));
  const attentionTaskCount = Number(runSnapshot?.attention_task_count || 0);
  const currentRunStatus = runSnapshot?.status || runSummary?.status || "running";

  async function triggerRetry() {
    setRetrySubmitting(true);
    setRetryFeedback(null);
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/retry`, {
        method: "POST",
      });
      const payload = (await response.json()) as Record<string, unknown>;
      if (!response.ok) {
        throw new Error(String(payload.detail || `retry failed (${response.status})`));
      }
      setRetryFeedback(`Retry started for ${runId}. Web 会继续自动跟踪这次恢复。`);
    } catch (error) {
      setRetryFeedback(error instanceof Error ? error.message : "Retry failed");
    } finally {
      setRetrySubmitting(false);
    }
  }

  const identityLookup = useMemo(() => {
    const byFull = new Map<string, IdentityOption>();
    const byAgentVariant = new Map<string, IdentityOption>();
    for (const row of identityOptions) {
      byFull.set(makeIdentityKey(row), row);
      byAgentVariant.set(`${row.agent_id}::${row.variant_id}`, row);
    }
    return { byFull, byAgentVariant };
  }, [identityOptions]);

  const taskRows = useMemo<EnrichedTaskRow[]>(() => {
    const raw = Array.isArray(runSnapshot?.task_monitor) ? runSnapshot.task_monitor : [];
    return raw.map((item) => {
      const row = item as Record<string, unknown>;
      const taskId = String(row.task_id || "-");
      const agentId = String(row.agent_id || "-");
      const variantId = String(row.variant_id || "default");
      const sampleId = row.sample_id == null ? "-" : String(row.sample_id);
      const model = String(row.model || "").trim() || identityLookup.byAgentVariant.get(`${agentId}::${variantId}`)?.model || null;
      const displayId =
        identityLookup.byFull.get(makeIdentityKey({ agent_id: agentId, variant_id: variantId, model }))?.display_id ||
        identityLookup.byAgentVariant.get(`${agentId}::${variantId}`)?.display_id ||
        makeDisplayId({ agent_id: agentId, variant_id: variantId, model });
      return {
        ...row,
        identityKey: makeIdentityKey({ agent_id: agentId, variant_id: variantId, model }),
        displayId,
        model,
        taskId,
        agentId,
        variantId,
        sampleId,
        status: String(row.status || "queued").toLowerCase(),
        durationMs: Number(row.duration_ms || 0),
        trialKey: makeTrialKey({
          task_id: taskId,
          agent_id: agentId,
          variant_id: variantId,
          sample_id: sampleId,
        }),
      };
    });
  }, [runSnapshot?.task_monitor, identityLookup]);

  const taskMatrixByMetric = useMemo(() => {
    const sums: Record<string, Record<string, Record<string, number>>> = {};
    const counts: Record<string, Record<string, Record<string, number>>> = {};
    for (const row of taskRows) {
      const metricsRaw = row.scorer_metrics;
      if (!metricsRaw || typeof metricsRaw !== "object" || Array.isArray(metricsRaw)) {
        continue;
      }
      const rowKey = view === "benchmark-first" ? row.taskId : row.displayId;
      const colKey = view === "benchmark-first" ? row.displayId : row.taskId;
      for (const [metricName, metricValue] of Object.entries(metricsRaw as Record<string, unknown>)) {
        const numeric = Number(metricValue);
        if (!Number.isFinite(numeric)) {
          continue;
        }
        if (!sums[metricName]) {
          sums[metricName] = {};
          counts[metricName] = {};
        }
        if (!sums[metricName][rowKey]) {
          sums[metricName][rowKey] = {};
          counts[metricName][rowKey] = {};
        }
        sums[metricName][rowKey][colKey] = (sums[metricName][rowKey][colKey] || 0) + numeric;
        counts[metricName][rowKey][colKey] = (counts[metricName][rowKey][colKey] || 0) + 1;
      }
    }
    const averaged: Record<string, Record<string, Record<string, number>>> = {};
    for (const [metricName, rowMap] of Object.entries(sums)) {
      averaged[metricName] = {};
      for (const [rowKey, colMap] of Object.entries(rowMap)) {
        averaged[metricName][rowKey] = {};
        for (const [colKey, total] of Object.entries(colMap)) {
          const count = counts[metricName]?.[rowKey]?.[colKey] || 1;
          averaged[metricName][rowKey][colKey] = total / Math.max(1, count);
        }
      }
    }
    return averaged;
  }, [taskRows, view]);

  const matrixMetricOrder = useMemo(() => {
    const seen = new Set<string>();
    const agents = Array.isArray(runSummary?.agents) ? runSummary.agents : [];
    for (const agent of agents) {
      const metrics = agent?.metrics;
      if (!metrics || typeof metrics !== "object") {
        continue;
      }
      for (const metricName of Object.keys(metrics)) {
        seen.add(metricName);
      }
    }
    for (const metricName of Object.keys(taskMatrixByMetric)) {
      seen.add(metricName);
    }
    return Array.from(seen).sort((lhs, rhs) => lhs.localeCompare(rhs));
  }, [runSummary?.agents, taskMatrixByMetric]);

  const filteredTaskRows = useMemo(() => {
    const q = taskSearch.trim().toLowerCase();
    return taskRows.filter((row) => {
      const isAttention =
        row.status === "error" ||
        ((row.status === "running" || row.status === "scoring") && row.durationMs >= 45_000) ||
        (currentRunStatus === "running" && row.status === "queued" && events.length > 0);
      if (taskAttentionOnly && !isAttention) {
        return false;
      }
      if (taskStatusFilter !== "all" && row.status !== taskStatusFilter) {
        return false;
      }
      if (identityFilter !== "all") {
        const sameIdentity = row.identityKey === identityFilter;
        const sameAgentVariant = `${row.agentId}::${row.variantId}` === identityFilter.split("::").slice(0, 2).join("::");
        if (!sameIdentity && !sameAgentVariant) {
          return false;
        }
      }
      if (!q) {
        return true;
      }
      const haystack = `${row.trialKey} ${row.displayId} ${row.model || ""} ${row.taskId} ${row.agentId} ${row.variantId} ${row.sampleId} ${row.status}`.toLowerCase();
      return haystack.includes(q);
    }).sort((lhs, rhs) => {
      const rank = (row: EnrichedTaskRow) => {
        if (row.status === "error") return 0;
        if (row.status === "running" || row.status === "scoring") return 1;
        if (row.status === "queued") return 2;
        return 3;
      };
      const diff = rank(lhs) - rank(rhs);
      if (diff !== 0) {
        return diff;
      }
      const lhsDuration = Number(lhs.durationMs || 0);
      const rhsDuration = Number(rhs.durationMs || 0);
      if (lhs.status === "running" || lhs.status === "scoring" || rhs.status === "running" || rhs.status === "scoring") {
        if (rhsDuration !== lhsDuration) {
          return rhsDuration - lhsDuration;
        }
      }
      return lhs.trialKey.localeCompare(rhs.trialKey);
    });
  }, [taskRows, taskSearch, taskStatusFilter, identityFilter, taskAttentionOnly, currentRunStatus, events.length]);

  const taskAttentionStats = useMemo(() => {
    let errorCount = 0;
    let longRunningCount = 0;
    let queuedCount = 0;
    for (const row of taskRows) {
      if (row.status === "error") {
        errorCount += 1;
      }
      if ((row.status === "running" || row.status === "scoring") && row.durationMs >= 45_000) {
        longRunningCount += 1;
      }
      if (row.status === "queued") {
        queuedCount += 1;
      }
    }
    const activeAttentionCount = errorCount + longRunningCount + (currentRunStatus === "running" ? queuedCount : 0);
    return {
      errorCount,
      longRunningCount,
      queuedCount,
      activeAttentionCount,
    };
  }, [taskRows, currentRunStatus]);

  const taskAttentionSummary = useMemo(() => {
    if (taskAttentionStats.errorCount > 0) {
      return {
        status: "Attention needed",
        reason: `${taskAttentionStats.errorCount} trial(s) failed and need diagnosis.`,
        next: "Open Trial Detail first, then Pretask and Runtime Logs for the same trial key.",
        variant: "danger" as const,
      };
    }
    if (taskAttentionStats.longRunningCount > 0) {
      return {
        status: "Possible stall",
        reason: `${taskAttentionStats.longRunningCount} running/scoring trial(s) have no progress for at least 45s.`,
        next: "Inspect Runtime Logs around pretask/runtime transitions, then open Pretask for latest stage.",
        variant: "warning" as const,
      };
    }
    if (currentRunStatus === "running" && taskAttentionStats.queuedCount > 0) {
      return {
        status: "Queue backlog",
        reason: `${taskAttentionStats.queuedCount} trial(s) are still queued while run is active.`,
        next: "Inspect scheduler/runtime capacity signals in Runtime Logs.",
        variant: "outline" as const,
      };
    }
    return {
      status: "Healthy",
      reason: "No immediate attention signal from task status and runtime duration.",
      next: "Continue monitoring Runtime Logs and sampled Trial Detail.",
      variant: "success" as const,
    };
  }, [taskAttentionStats, currentRunStatus]);

  const filteredRuntimeEvents = useMemo(() => {
    const q = runtimeSearch.trim().toLowerCase();
    const normalizedIdentityPrefix = identityFilter === "all" ? null : identityFilter.split("::").slice(0, 2).join("::");
    const rows = events.filter((event) => {
      const eventName = String(event.event || "").toLowerCase();
      const message = String(event.message || "").toLowerCase();
      const agentId = String(event.agent_id || "-");
      const variantId = String(event.variant_id || "default");
      const model = String(event.model || "").trim() || null;
      const eventIdentityKey = makeIdentityKey({ agent_id: agentId, variant_id: variantId, model });
      const eventIdentityPrefix = `${agentId}::${variantId}`;
      const displayId =
        identityLookup.byFull.get(eventIdentityKey)?.display_id ||
        identityLookup.byAgentVariant.get(eventIdentityPrefix)?.display_id ||
        makeDisplayId({ agent_id: agentId, variant_id: variantId, model });

      if (runtimeEventFilter === "all" && eventName === "ui.heartbeat") {
        return false;
      }
      if (identityFilter !== "all" && eventIdentityKey !== identityFilter && eventIdentityPrefix !== normalizedIdentityPrefix) {
        return false;
      }
      if (runtimeEventFilter !== "all") {
        if (runtimeEventFilter === "attention") {
          const hasError =
            eventName.includes("error") ||
            eventName.includes("failed") ||
            eventName.startsWith("pretask.") ||
            eventName.startsWith("runtime.env.") ||
            message.includes("error") ||
            message.includes("failed") ||
            message.includes("timeout");
          if (!hasError) {
            return false;
          }
        }
        if (runtimeEventFilter === "pretask" && !eventName.startsWith("pretask.")) {
          return false;
        }
        if (runtimeEventFilter === "trial" && !(eventName.includes("trial") || eventName.includes("task"))) {
          return false;
        }
        if (runtimeEventFilter === "model" && !(eventName.includes("model") || model)) {
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
      const raw = JSON.stringify(event).toLowerCase();
      return `${eventName} ${message} ${displayId.toLowerCase()} ${(model || "").toLowerCase()} ${raw}`.includes(q);
    });
    if (runtimeEventFilter !== "all") {
      return rows;
    }
    return rows.slice().sort((lhs, rhs) => {
      const lhsName = String(lhs.event || "").toLowerCase();
      const rhsName = String(rhs.event || "").toLowerCase();
      const lhsMessage = String(lhs.message || "").toLowerCase();
      const rhsMessage = String(rhs.message || "").toLowerCase();
      const lhsError = lhsName.includes("error") || lhsName.includes("failed") || lhsMessage.includes("error");
      const rhsError = rhsName.includes("error") || rhsName.includes("failed") || rhsMessage.includes("error");
      if (lhsError !== rhsError) {
        return lhsError ? -1 : 1;
      }
      const lhsTs = Number(lhs.ts_ms || 0);
      const rhsTs = Number(rhs.ts_ms || 0);
      return rhsTs - lhsTs;
    });
  }, [events, runtimeSearch, runtimeEventFilter, identityFilter, identityLookup]);

  const taskContainerRef = useRef<HTMLDivElement | null>(null);
  const taskVirtualizer = useVirtualizer({
    count: filteredTaskRows.length,
    getScrollElement: () => taskContainerRef.current,
    estimateSize: () => 108,
    measureElement: (el) => el?.getBoundingClientRect().height ?? 0,
    overscan: 12,
  });

  useEffect(() => {
    if (!selectedTrialKey) {
      return;
    }
    const index = filteredTaskRows.findIndex((row) => row.trialKey === selectedTrialKey);
    if (index < 0) {
      return;
    }
    taskVirtualizer.scrollToIndex(index, { align: "center" });
  }, [selectedTrialKey, filteredTaskRows, taskVirtualizer]);

  const runTitle = runSnapshot?.run_id || runSummary?.run_id || runId;
  const benchmark = runSnapshot?.benchmark || runSummary?.benchmark || "-";
  const status = currentRunStatus;
  const updatedAt = runSnapshot?.updated_at_ms;

  useEffect(() => {
    const rawTab = (searchParams.get("tab") || "").trim().toLowerCase();
    const nextTab: "overview" | "tasks" | "runtime" | "trial_detail" =
      rawTab === "overview" || rawTab === "runtime" || rawTab === "trial_detail" ? (rawTab as "overview" | "runtime" | "trial_detail") : "tasks";
    const nextTrialKey = (searchParams.get("trial_key") || "").trim();
    setActiveTab((prev) => (prev === nextTab ? prev : nextTab));
    setSelectedTrialKey((prev) => (prev === nextTrialKey ? prev : nextTrialKey));
    setTrialKeyInput((prev) => (prev === nextTrialKey ? prev : nextTrialKey));
  }, [searchParams]);

  const runMetadataCard = (
    <Card className="rounded-[28px] border-white/80 bg-white/92 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
      <CardHeader>
        <CardTitle className="text-3xl tracking-tight">Run Metadata</CardTitle>
        <CardDescription className="text-base leading-7">把这次 run 的状态、模型集合、标识与更新时间集中放在一起。</CardDescription>
      </CardHeader>
      <CardContent className="text-base text-muted-foreground">
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(255,255,255,0.9),rgba(241,245,249,0.85))] p-4">
            <div className="mb-2 flex items-center gap-1 text-sm uppercase tracking-[0.16em] text-foreground/80">
              <Activity className="h-4 w-4" />
              Status
            </div>
            <div className="text-xl font-semibold text-foreground">status={status}</div>
            <div className="mt-1">progress={runSnapshot?.done || 0}/{runSnapshot?.total || 0}</div>
          </div>
          <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(236,253,245,0.9),rgba(255,255,255,0.85))] p-4">
            <div className="mb-2 text-sm uppercase tracking-[0.16em] text-foreground/80">Models</div>
            <div className="text-xl font-semibold text-foreground">{selectedVariantCount} variants</div>
            <div className="mt-1 line-clamp-3 text-sm" title={selectedModels.join(", ") || "-"}>
              {selectedModels.length > 0
                ? selectedModels.map((model) => truncateMiddle(model, 34, 16, 12)).join(", ")
                : "-"}
            </div>
          </div>
          <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(239,246,255,0.9),rgba(255,255,255,0.85))] p-4">
            <div className="mb-2 text-sm uppercase tracking-[0.16em] text-foreground/80">Identifiers</div>
            <div className="font-[family-name:var(--font-mono)] text-sm text-foreground" title={runTitle}>
              {truncateMiddle(runTitle, 52, 24, 22)}
            </div>
            <div className="mt-1 text-sm">benchmark={benchmark}</div>
          </div>
          <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(250,245,255,0.9),rgba(255,255,255,0.85))] p-4">
            <div className="mb-2 flex items-center gap-1 text-sm uppercase tracking-[0.16em] text-foreground/80">
              <CalendarClock className="h-4 w-4" />
              Updated
            </div>
            <div className="text-xl font-semibold text-foreground">{formatDateTime(updatedAt)}</div>
            <div
              className="mt-1 font-[family-name:var(--font-mono)] text-sm text-muted-foreground"
              title={String(runSnapshot?.last_event_id || "-")}
            >
              event={truncateMiddle(String(runSnapshot?.last_event_id || "-"), 40, 14, 14)}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  const taskMonitorCard = (
    <Card className="rounded-[28px] border-white/80 bg-white/92 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-3xl tracking-tight">Tasks</CardTitle>
            <CardDescription className="text-base leading-7">
              当前计划 {plannedTrials} 个 trials / {plannedTaskCount || "-"} 个 tasks{attentionTaskCount > 0 ? `，其中 ${attentionTaskCount} 个需要优先关注` : ""}，先筛选模型与状态，再进入具体 trial 细节。
            </CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={() => snapshotQuery.refetch()}>
            <RefreshCw className="mr-1 h-4 w-4" />
            刷新
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="sticky top-3 z-10 grid gap-3 rounded-[24px] border bg-white/95 p-4 shadow-sm backdrop-blur md:grid-cols-12">
          <div className="space-y-1 md:col-span-4">
            <div className="text-sm font-medium text-muted-foreground">Search tasks</div>
            <Input
              value={taskSearch}
              onChange={(event) => setTaskSearch(event.target.value)}
              placeholder="Search task, model, variant, sample, trial key"
              className="h-12 rounded-xl bg-white"
            />
          </div>
          <div className="space-y-1 md:col-span-3">
            <div className="text-sm font-medium text-muted-foreground">Identity</div>
            <Select value={identityFilter} onChange={(event) => setIdentityFilter(event.target.value)} className="h-12 rounded-xl bg-white">
              <option value="all">All models</option>
              {identityOptions.map((row) => (
                <option key={makeIdentityKey(row)} value={makeIdentityKey(row)}>
                  {row.display_id}{row.model ? ` (${row.model})` : ""}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1 md:col-span-2">
            <div className="text-sm font-medium text-muted-foreground">Status</div>
            <Select
              value={taskStatusFilter}
              onChange={(event) => setTaskStatusFilter(event.target.value)}
              className="h-12 rounded-xl bg-white"
            >
              <option value="all">All status</option>
              <option value="queued">Queued</option>
              <option value="running">Running</option>
              <option value="scoring">Scoring</option>
              <option value="success">Success</option>
              <option value="error">Error</option>
            </Select>
          </div>
          <div className="space-y-1 md:col-span-2">
            <div className="text-sm font-medium text-muted-foreground">Attention filter</div>
            <Button
              type="button"
              variant={taskAttentionOnly ? "default" : "outline"}
              className="h-12 w-full rounded-xl"
              onClick={() => setTaskAttentionOnly((value) => !value)}
            >
              {taskAttentionOnly ? "Attention only" : "Show all"}
            </Button>
          </div>
          <div className="flex items-end md:col-span-1">
            <div className="flex h-12 w-full items-center justify-center rounded-xl border bg-white px-3 text-base text-muted-foreground">
              {filteredTaskRows.length}/{taskRows.length}
            </div>
          </div>
        </div>
        <div
          className={cn(
            "rounded-2xl border p-4",
            taskAttentionSummary.variant === "danger"
              ? "border-rose-300 bg-rose-50/80"
              : taskAttentionSummary.variant === "warning"
                ? "border-amber-300 bg-amber-50/80"
                : taskAttentionSummary.variant === "outline"
                  ? "border-slate-300 bg-slate-50/80"
                  : "border-emerald-300 bg-emerald-50/80",
          )}
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={taskAttentionSummary.variant}>{taskAttentionSummary.status}</Badge>
            <span className="text-sm text-muted-foreground">
              {taskAttentionStats.activeAttentionCount > 0
                ? `${taskAttentionStats.activeAttentionCount} task(s) currently need attention`
                : "No immediate attention task"}
            </span>
          </div>
          <div className="mt-1 text-base font-medium text-foreground">{taskAttentionSummary.reason}</div>
          <div className="mt-1 text-sm text-muted-foreground">Next step: {taskAttentionSummary.next}</div>
        </div>
        <div className="rounded-xl border bg-white/70 px-4 py-2 text-sm text-muted-foreground">
          Showing {taskAttentionOnly ? "attention-only tasks" : "all matched tasks"} · {taskStatusFilter === "all" ? "all status" : taskStatusFilter} ·{" "}
          {identityFilter === "all" ? "all identities" : "selected identity"}
          {taskSearch.trim() ? ` · query "${taskSearch.trim()}"` : ""}
        </div>
        {selectedTrialKey && !filteredTaskRows.some((row) => row.trialKey === selectedTrialKey) && taskRows.some((row) => row.trialKey === selectedTrialKey) ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50/80 px-4 py-3">
            <div className="text-sm text-amber-900">
              当前选中的 trial 不在过滤结果里。你可以清空筛选后重新定位它。
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setTaskSearch("");
                setTaskStatusFilter("all");
                setTaskAttentionOnly(false);
                setIdentityFilter("all");
              }}
            >
              清空筛选
            </Button>
          </div>
        ) : null}
        <div ref={taskContainerRef} className="h-[560px] overflow-auto rounded-[24px] border bg-[linear-gradient(180deg,rgba(248,250,252,0.75),rgba(255,255,255,0.92))]">
          <div style={{ height: `${taskVirtualizer.getTotalSize()}px`, position: "relative" }}>
            {taskVirtualizer.getVirtualItems().map((item) => {
              const row = filteredTaskRows[item.index];
              const statusVariant = (row.status === "success"
                ? "success"
                : row.status === "error"
                  ? "danger"
                  : row.status === "running"
                    ? "warning"
                    : row.status === "scoring"
                    ? "warning"
                    : "outline") as "success" | "danger" | "warning" | "outline";
              const longRunning = (row.status === "running" || row.status === "scoring") && row.durationMs >= 45_000;
              return (
                <div
                  key={`${row.trialKey}-${item.index}`}
                  ref={taskVirtualizer.measureElement}
                  data-index={item.index}
                  className={`absolute left-0 top-0 w-full border-b px-5 py-4 ${row.status === "error" ? "bg-rose-50/80" : longRunning ? "bg-amber-50/80" : item.index % 2 === 0 ? "bg-white/70" : "bg-slate-50/55"} ${selectedTrialKey && row.trialKey === selectedTrialKey ? "ring-2 ring-primary/35 ring-inset" : ""}`}
                  style={{ transform: `translateY(${item.start}px)` }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="font-semibold text-lg leading-7">{row.displayId}</div>
                          <Badge variant={statusVariant}>{row.status}</Badge>
                          {row.model ? <Badge variant="outline">{row.model}</Badge> : null}
                          {longRunning ? <Badge variant="warning">long-running</Badge> : null}
                          {row.status === "scoring" ? <Badge variant="outline">in scorer</Badge> : null}
                        </div>
                      <div className="flex flex-wrap items-center gap-2 text-[13px] leading-6 text-muted-foreground md:text-sm">
                        <span className="rounded-md border bg-muted/25 px-2 py-0.5" title={row.taskId}>
                          task {truncateMiddle(row.taskId, 32, 14, 12)}
                        </span>
                        <span className="rounded-md border bg-muted/25 px-2 py-0.5" title={row.variantId}>
                          variant {truncateMiddle(row.variantId, 24, 10, 8)}
                        </span>
                        <span className="rounded-md border bg-muted/25 px-2 py-0.5" title={row.sampleId}>
                          sample {truncateMiddle(row.sampleId, 28, 12, 10)}
                        </span>
                        <span className="rounded-md border bg-muted/25 px-2 py-0.5">
                          duration {row.durationMs}ms
                        </span>
                      </div>
                      <div
                        className="font-[family-name:var(--font-mono)] text-[13px] leading-6 text-muted-foreground"
                        title={row.trialKey}
                      >
                        trial {truncateMiddle(row.trialKey, 72, 30, 28)}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2 self-start">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setQuickPeekTrialKey(row.trialKey);
                          setSelectedTrialKey(row.trialKey);
                          setTrialKeyInput(row.trialKey);
                          setActiveTab("tasks");
                          syncWorkspaceUrl({ tab: "tasks", trialKey: row.trialKey });
                          setQuickPeekOpen(true);
                        }}
                      >
                        查看详情
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          openWorkspaceTrialDetail(row.trialKey);
                        }}
                      >
                        Trial Detail
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setDrawerTrialKey(row.trialKey);
                          setSelectedTrialKey(row.trialKey);
                          setTrialKeyInput(row.trialKey);
                          syncWorkspaceUrl({ tab: "tasks", trialKey: row.trialKey });
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
            <div className="p-4 text-base text-muted-foreground">没有匹配项，试试切换模型过滤或放宽关键字。</div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );

  const runtimeLogsCard = (
    <Card className="rounded-[28px] border-white/80 bg-white/92 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
      <CardHeader>
        <CardTitle className="text-3xl tracking-tight">Runtime Logs</CardTitle>
        <CardDescription className="text-base leading-7">先看异常，再按事件类型和模型收窄，适合快速定位启动或评测过程里的问题。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 rounded-[24px] border bg-muted/20 p-4 md:grid-cols-12">
          <div className="space-y-1 md:col-span-5">
            <div className="text-sm font-medium text-muted-foreground">Search runtime logs</div>
            <Input
              value={runtimeSearch}
              onChange={(event) => setRuntimeSearch(event.target.value)}
              placeholder="Search event summary, message, model, task, trial key"
              className="h-12 rounded-xl bg-white"
            />
          </div>
          <div className="space-y-1 md:col-span-3">
            <div className="text-sm font-medium text-muted-foreground">Identity</div>
            <Select value={identityFilter} onChange={(event) => setIdentityFilter(event.target.value)} className="h-12 rounded-xl bg-white">
              <option value="all">All models</option>
              {identityOptions.map((row) => (
                <option key={makeIdentityKey(row)} value={makeIdentityKey(row)}>
                  {row.display_id}{row.model ? ` (${row.model})` : ""}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1 md:col-span-3">
            <div className="text-sm font-medium text-muted-foreground">Event focus</div>
            <Select
              value={runtimeEventFilter}
              onChange={(event) => setRuntimeEventFilter(event.target.value)}
              className="h-12 rounded-xl bg-white"
            >
              <option value="attention">Attention first</option>
              <option value="all">All events</option>
              <option value="pretask">Pretask</option>
              <option value="trial">Trial / task</option>
              <option value="model">Model</option>
              <option value="error">Errors only</option>
            </Select>
          </div>
          <div className="flex items-end md:col-span-1">
            <div className="flex h-12 w-full items-center justify-center rounded-xl border bg-white px-3 text-base text-muted-foreground">
              {filteredRuntimeEvents.length}/{events.length}
            </div>
          </div>
        </div>
        <div className="rounded-xl border bg-white/70 px-4 py-2 text-sm text-muted-foreground">
          Showing {runtimeEventFilter === "attention" ? "attention-priority events" : runtimeEventFilter} · {identityFilter === "all" ? "all identities" : "selected identity"}
          {runtimeSearch.trim() ? ` · query "${runtimeSearch.trim()}"` : ""}
        </div>
        <VirtualLogViewer events={filteredRuntimeEvents} />
        <div className="flex flex-col gap-3 rounded-2xl border bg-white/80 p-3 md:flex-row md:items-end">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="text-sm font-medium text-muted-foreground">Jump to Trial Detail</div>
          <Input
            value={trialKeyInput}
            onChange={(e) => setTrialKeyInput(e.target.value)}
              placeholder="task::agent::variant::sample"
              className="h-12 font-[family-name:var(--font-mono)] text-base"
          />
          </div>
          <Button
            variant="outline"
            className="h-12"
            onClick={() => {
              if (!trialKeyInput.trim()) {
                return;
              }
              openWorkspaceTrialDetail(trialKeyInput.trim());
            }}
          >
            查看详情
          </Button>
          <Button
            variant="outline"
            className="h-12"
            onClick={() => {
              if (!trialKeyInput.trim()) {
                return;
              }
              setDrawerTrialKey(trialKeyInput.trim());
              setSelectedTrialKey(trialKeyInput.trim());
              syncWorkspaceUrl({ tab: "runtime", trialKey: trialKeyInput.trim() });
              setDrawerOpen(true);
            }}
          >
            打开 Pretask
          </Button>
        </div>
      </CardContent>
    </Card>
  );

  const workspaceTrialDetailCard = (
    <TrialDetailPanel
      title="Trial Detail"
      trialKey={selectedTrialKey}
      detail={(trialDetailQuery.data as Record<string, unknown> | null) || null}
      loading={Boolean(selectedTrialKey) && trialDetailQuery.isLoading}
      isError={Boolean(selectedTrialKey) && trialDetailQuery.isError}
      onOpenPretask={(trialKey) => {
        if (!trialKey.trim()) {
          return;
        }
        setDrawerTrialKey(trialKey);
        setTrialKeyInput(trialKey);
        setSelectedTrialKey(trialKey);
        setDrawerOpen(true);
        syncWorkspaceUrl({ tab: "trial_detail", trialKey });
      }}
      onBackToTasks={(trialKey) => {
        setSelectedTrialKey(trialKey);
        setTrialKeyInput(trialKey);
        setActiveTab("tasks");
        syncWorkspaceUrl({ tab: "tasks", trialKey });
      }}
    />
  );

  if (runSummaryQuery.isError || snapshotQuery.isError) {
    return (
      <main className="mx-auto max-w-[1600px] px-5 py-6 md:px-10 md:py-8">
        <Card className="rounded-[28px] border-dashed">
          <CardHeader>
            <CardTitle className="text-3xl">找不到这个 run</CardTitle>
            <CardDescription>这个 run 可能已经被清理，或者当前监控项目下不存在它。</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            <Link href="/" className={cn(buttonVariants({ variant: "default" }))}>
              返回 Runs
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-[1880px] px-5 py-6 md:px-10 md:py-8">
      <header className="mb-6 overflow-hidden rounded-[34px] border border-white/80 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.18),transparent_32%),radial-gradient(circle_at_top_right,rgba(6,182,212,0.18),transparent_28%),linear-gradient(165deg,rgba(248,255,252,0.98),rgba(239,250,255,0.95))] p-7 shadow-[0_24px_80px_rgba(15,118,110,0.12)] md:p-9">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-5xl space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <Link href="/" className={cn(buttonVariants({ variant: "outline" }), "h-11 rounded-full px-5")}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                返回 Runs
              </Link>
              <Link href="/compare" className={cn(buttonVariants({ variant: "outline" }), "h-11 rounded-full px-5")}>
                历史对比
              </Link>
              <Button
                variant="outline"
                className="h-11 rounded-full px-5"
                disabled={retrySubmitting || (status === "running" && Boolean(runSnapshot?.runner_alive))}
                onClick={() => void triggerRetry()}
              >
                {retrySubmitting ? "Retrying..." : "Retry this run"}
              </Button>
            </div>
            <div>
              <h1 className="text-5xl font-semibold tracking-[-0.04em] md:text-6xl">{benchmark} Run Workspace</h1>
              <p className="mt-3 font-[family-name:var(--font-mono)] text-base text-muted-foreground md:text-lg" title={runTitle}>
                {truncateMiddle(runTitle, 108, 54, 50)}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant={status === "running" ? "warning" : status === "cancelled" || status === "zombie" || progress.failed > 0 ? "danger" : "success"}>{status}</Badge>
              <Badge variant="outline">{benchmark}</Badge>
              <Badge variant="outline">variants {selectedVariantCount}</Badge>
              {status === "running" && runSnapshot?.stalled ? <Badge variant="danger">no recent progress</Badge> : null}
              {runSnapshot?.heartbeat_only ? <Badge variant="warning">heartbeat only</Badge> : null}
              {runSnapshot?.observer_stale ? <Badge variant="warning">observer stale</Badge> : null}
              {status === "running" && runSnapshot?.runner_alive ? <Badge variant="outline">runner alive</Badge> : null}
              {status === "zombie" ? <Badge variant="danger">historical zombie</Badge> : null}
              {attentionTaskCount > 0 ? <Badge variant="warning">{attentionTaskCount} tasks need attention</Badge> : null}
              {recoverableTrials > 0 ? <Badge variant="warning">{recoverableTrials} recoverable</Badge> : null}
              {recoveredTrials > 0 ? <Badge variant="success">{recoveredTrials} recovered</Badge> : null}
              {stillFailingTrials > 0 ? <Badge variant="danger">{stillFailingTrials} still failing</Badge> : null}
              {selectedModels.map((model) => (
                <Badge key={model} variant="outline" className="max-w-[320px] truncate">
                  {model}
                </Badge>
              ))}
            </div>
            {retryFeedback ? <p className="text-sm text-muted-foreground">{retryFeedback}</p> : null}
          </div>
          <div className="grid gap-3 rounded-[28px] border border-white/80 bg-white/80 p-4 shadow-sm md:min-w-[320px]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm uppercase tracking-[0.18em] text-muted-foreground">Live connection</div>
                <div className="mt-1 text-2xl font-semibold">{connected ? "Connected" : "Reconnecting"}</div>
              </div>
              <Badge variant={connected ? "success" : "warning"}>{connected ? "SSE connected" : "SSE reconnecting"}</Badge>
            </div>
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
              <div className="rounded-2xl border bg-muted/25 p-3">
                <div className="text-sm text-muted-foreground">Events</div>
                <div className="mt-2 text-3xl font-semibold">{events.length}</div>
              </div>
              <div className="rounded-2xl border bg-muted/25 p-3">
                <div className="text-sm text-muted-foreground">Updated</div>
                <div className="mt-2 text-base font-semibold">{formatDateTime(updatedAt)}</div>
              </div>
              <div className="rounded-2xl border bg-muted/25 p-3">
                <div className="text-sm text-muted-foreground">Planned trials</div>
                <div className="mt-2 text-3xl font-semibold">{plannedTrials}</div>
              </div>
              <div className="rounded-2xl border bg-muted/25 p-3">
                <div className="text-sm text-muted-foreground">Visible tasks</div>
                <div className="mt-2 text-3xl font-semibold">{runSnapshot?.visible_task_rows || taskRows.length}</div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
              <div className="rounded-2xl border bg-muted/25 p-3">
                <div className="text-sm text-muted-foreground">Recoverable</div>
                <div className="mt-2 text-3xl font-semibold">{recoverableTrials}</div>
              </div>
              <div className="rounded-2xl border bg-muted/25 p-3">
                <div className="text-sm text-muted-foreground">Recovered</div>
                <div className="mt-2 text-3xl font-semibold text-success">{recoveredTrials}</div>
              </div>
              <div className="rounded-2xl border bg-muted/25 p-3">
                <div className="text-sm text-muted-foreground">Still failing</div>
                <div className="mt-2 text-3xl font-semibold text-danger">{stillFailingTrials}</div>
              </div>
              <div className="rounded-2xl border bg-muted/25 p-3">
                <div className="text-sm text-muted-foreground">Retry attempts</div>
                <div className="mt-2 text-3xl font-semibold">{retriedTrials}</div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <section className="space-y-4">
        <Card className="rounded-[28px] border-white/80 bg-white/92 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
          <CardHeader className="pb-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle className="text-3xl tracking-tight">Workspace</CardTitle>
                <CardDescription className="text-base leading-7">
                  updated={formatDateTime(updatedAt)} | planned={plannedTrials} trials{runSummary?.experiment_id ? ` | experiment=${runSummary.experiment_id}` : ""}
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <label className="text-base text-muted-foreground">View</label>
                <Select
                  value={view}
                  onChange={(e) => setView((e.target.value as "variant-first" | "benchmark-first") || "variant-first")}
                  className="h-11 w-[180px] rounded-xl bg-white"
                >
                  <option value="variant-first">By model</option>
                  <option value="benchmark-first">By task</option>
                </Select>
              </div>
            </div>
            <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-4">
              {[
                { key: "overview", label: "Overview", hint: "整体进度、模型分布与总量" },
                { key: "tasks", label: "Tasks", hint: `${filteredTaskRows.length}/${taskRows.length} task rows` },
                { key: "runtime", label: "Runtime Logs", hint: `${runtimeEventFilter === "attention" ? "attention-first · " : ""}${filteredRuntimeEvents.length}/${events.length} live events` },
                { key: "trial_detail", label: "Trial Detail", hint: selectedTrialKey ? `selected ${truncateMiddle(selectedTrialKey, 40, 16, 14)}` : "choose a trial from tasks" },
              ].map((tab) => {
                const active = activeTab === tab.key;
                return (
                  <button
                    key={tab.key}
                    onClick={() => {
                      const nextTab = tab.key as "overview" | "tasks" | "runtime" | "trial_detail";
                      setActiveTab(nextTab);
                      syncWorkspaceUrl({ tab: nextTab });
                    }}
                    className={cn(
                      "min-h-[78px] rounded-[22px] border px-5 py-4 text-left transition",
                      active
                        ? "border-primary bg-primary text-primary-foreground shadow-[0_14px_34px_rgba(13,148,136,0.22)]"
                        : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <div className="text-xl font-semibold">{tab.label}</div>
                    <div className="mt-1 text-sm opacity-90">{tab.hint}</div>
                  </button>
                );
              })}
            </div>
          </CardHeader>
        </Card>

        {activeTab === "overview" ? (
          <>
            <Card className="rounded-[28px] border-white/80 bg-white/92 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
              <CardHeader>
                <CardTitle className="text-3xl tracking-tight">Run Summary</CardTitle>
                <CardDescription className="text-base leading-7">
                  Live summary based on scored trials. 整体进度和模型统计现在共用同一条运行中数据链。
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                  <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(240,253,250,0.95),rgba(255,255,255,0.92))] p-4">
                    <div className="text-base text-muted-foreground">Overall Progress</div>
                    <div className="mt-2 text-4xl font-semibold">{formatPercent(completionRate)}</div>
                    <div className="mt-1 text-sm text-muted-foreground">
                      {progress.done}/{progress.total}
                    </div>
                  </div>
                  <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(255,251,235,0.95),rgba(255,255,255,0.92))] p-4">
                    <div className="text-base text-muted-foreground">Running</div>
                    <div className="mt-2 text-4xl font-semibold text-warning">{progress.running}</div>
                  </div>
                  <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(236,253,245,0.95),rgba(255,255,255,0.92))] p-4">
                    <div className="text-base text-muted-foreground">Completed</div>
                    <div className="mt-2 text-4xl font-semibold text-success">{progress.completed}</div>
                  </div>
                  <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(255,241,242,0.95),rgba(255,255,255,0.92))] p-4">
                    <div className="text-base text-muted-foreground">Failed</div>
                    <div className="mt-2 text-4xl font-semibold text-danger">{progress.failed}</div>
                  </div>
                  <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(239,246,255,0.95),rgba(255,255,255,0.92))] p-4">
                    <div className="text-base text-muted-foreground">Variant Count</div>
                    <div className="mt-2 text-4xl font-semibold">{selectedVariantCount}</div>
                  </div>
                  <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(245,243,255,0.95),rgba(255,255,255,0.92))] p-4">
                    <div className="text-base text-muted-foreground">Scored Trials</div>
                    <div className="mt-2 text-4xl font-semibold">{scoredTrials}</div>
                    <div className="mt-1 text-sm text-muted-foreground">
                      {scoredTrials}/{plannedTrials || progress.total}
                    </div>
                  </div>
                  <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(255,251,235,0.95),rgba(255,255,255,0.92))] p-4">
                    <div className="text-base text-muted-foreground">Recoverable</div>
                    <div className="mt-2 text-4xl font-semibold text-warning">{recoverableTrials}</div>
                    <div className="mt-1 text-sm text-muted-foreground">unfinished + non-success effective</div>
                  </div>
                  <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(236,253,245,0.95),rgba(255,255,255,0.92))] p-4">
                    <div className="text-base text-muted-foreground">Recovered</div>
                    <div className="mt-2 text-4xl font-semibold text-success">{recoveredTrials}</div>
                    <div className="mt-1 text-sm text-muted-foreground">latest effective attempt is success</div>
                  </div>
                  <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(255,241,242,0.95),rgba(255,255,255,0.92))] p-4">
                    <div className="text-base text-muted-foreground">Still failing</div>
                    <div className="mt-2 text-4xl font-semibold text-danger">{stillFailingTrials}</div>
                    <div className="mt-1 text-sm text-muted-foreground">retried but not yet healthy</div>
                  </div>
                  <div className="rounded-[24px] border bg-[linear-gradient(180deg,rgba(239,246,255,0.95),rgba(255,255,255,0.92))] p-4">
                    <div className="text-base text-muted-foreground">Retry Attempts</div>
                    <div className="mt-2 text-4xl font-semibold">{retriedTrials}</div>
                    <div className="mt-1 text-sm text-muted-foreground">trials with attempt history &gt; 1</div>
                  </div>
                </div>

                <div className="mt-5">
                  <div className="mb-2 flex items-center gap-2 text-base font-medium">
                    <FlaskConical className="h-4 w-4 text-primary" />
                    Model Ranking
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    {scoredTrials === 0 ? (
                      <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                        Waiting for first scored trial. 首个 scorer 结果到达后，这里的模型分数会开始实时波动。
                      </div>
                    ) : topIdentities.length === 0 ? (
                      <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">暂无 ranking 数据。</div>
                    ) : (
                      topIdentities.map((agent) => (
                        <div key={`${agent.display_id}-${agent.model || "-"}`} className="rounded-2xl border p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="font-[family-name:var(--font-mono)] text-base" title={agent.display_id}>
                              {truncateMiddle(agent.display_id, 72, 34, 32)}
                            </div>
                            {agent.model ? <Badge variant="outline">{agent.model}</Badge> : null}
                          </div>
                          <div className="mt-2 flex items-center justify-between text-base">
                            <span className="text-muted-foreground">rank score</span>
                            <span className="font-semibold">{agent.rank_score.toFixed(4)}</span>
                          </div>
                          <div className="mt-1 text-sm text-muted-foreground">
                            score based on {Number(agent.scored_trials || 0)} scored trials
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-[28px] border-white/80 bg-white/92 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
              <CardHeader>
                <CardTitle className="text-3xl tracking-tight">Task Matrix</CardTitle>
                <CardDescription className="text-base leading-7">
                  {scoredTrials === 0
                    ? "Waiting for first scored trial. 当前矩阵会在第一个 scorer 结果出现后开始刷新。"
                    : view === "variant-first"
                      ? "按模型横向对比每个 task 的当前平均结果。"
                      : "按 task 反向查看不同模型的当前平均表现。"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <MatrixBarChart
                  matrix={runSummary?.matrix || {}}
                  matrixByMetric={taskMatrixByMetric}
                  metricOrder={matrixMetricOrder}
                  rowLabel={view === "variant-first" ? "Variant / Model" : "Task"}
                  seriesLabel={view === "variant-first" ? "Task" : "Variant / Model"}
                />
              </CardContent>
            </Card>

            {runMetadataCard}
          </>
        ) : null}

        {activeTab === "tasks" ? (
          <>
            {taskMonitorCard}
            {runMetadataCard}
          </>
        ) : null}

        {activeTab === "runtime" ? (
          <>
            {runtimeLogsCard}
            {runMetadataCard}
          </>
        ) : null}

        {activeTab === "trial_detail" ? (
          <>
            {workspaceTrialDetailCard}
            {runMetadataCard}
          </>
        ) : null}
      </section>

      <PretaskDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        runId={runId}
        trialKey={drawerTrialKey}
        items={pretaskQuery.data?.items || []}
        loading={pretaskQuery.isLoading}
      />
      <TrialQuickPeekDrawer
        open={quickPeekOpen}
        onClose={() => setQuickPeekOpen(false)}
        runId={runId}
        trialKey={quickPeekTrialKey}
        detail={(quickPeekTrialQuery.data as Record<string, unknown> | null) || null}
        loading={quickPeekTrialQuery.isLoading}
        onOpenDetailPage={(trialKey) => {
          const normalized = trialKey.trim();
          if (!normalized) {
            return;
          }
          router.push(`/runs/${encodeURIComponent(runId)}/trial?trial_key=${encodeURIComponent(normalized)}`);
        }}
        onOpenWorkspaceDetail={(trialKey) => {
          openWorkspaceTrialDetail(trialKey);
        }}
      />
    </main>
  );
}
