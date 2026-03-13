"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";

import { PretaskDrawer } from "@/components/pretask-drawer";
import { TrialDetailPanel } from "@/components/trial-detail-panel";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn, formatDateTime, truncateMiddle } from "@/lib/utils";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status}): ${url}`);
  }
  return (await response.json()) as T;
}

export function RunTrialDetailPage({ runId }: { runId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const trialKeyFromUrl = useMemo(() => (searchParams.get("trial_key") || "").trim(), [searchParams]);
  const [trialKeyInput, setTrialKeyInput] = useState(trialKeyFromUrl);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTrialKey, setDrawerTrialKey] = useState(trialKeyFromUrl);

  useEffect(() => {
    setTrialKeyInput(trialKeyFromUrl);
  }, [trialKeyFromUrl]);

  const snapshotQuery = useQuery({
    queryKey: ["snapshot", runId],
    queryFn: () => fetchJson<Record<string, unknown>>(`/api/runs/${encodeURIComponent(runId)}/snapshot`),
    enabled: Boolean(runId),
    refetchInterval: 2_000,
  });

  const trialDetailQuery = useQuery({
    queryKey: ["trial-detail-page", runId, trialKeyFromUrl],
    queryFn: () =>
      fetchJson<Record<string, unknown>>(
        `/api/runs/${encodeURIComponent(runId)}/trial?trial_key=${encodeURIComponent(trialKeyFromUrl)}`,
      ),
    enabled: Boolean(runId && trialKeyFromUrl),
    refetchInterval: trialKeyFromUrl ? 2_000 : false,
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

  const benchmark = String(snapshotQuery.data?.benchmark || "-");
  const updatedAt = Number(snapshotQuery.data?.updated_at_ms || 0) || null;

  return (
    <main className="mx-auto max-w-[1880px] px-5 py-6 md:px-10 md:py-8">
      <header className="mb-6 rounded-[28px] border border-white/80 bg-white/90 p-6 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-2">
            <Link
              href={`/runs/${encodeURIComponent(runId)}?tab=tasks${trialKeyFromUrl ? `&trial_key=${encodeURIComponent(trialKeyFromUrl)}` : ""}`}
              className={cn(buttonVariants({ variant: "outline" }), "h-10 rounded-full px-4")}
            >
              <ArrowLeft className="mr-1 h-4 w-4" />
              返回 Tasks
            </Link>
            <CardTitle className="text-3xl tracking-tight">Trial Detail Page</CardTitle>
            <CardDescription className="text-base">
              run={truncateMiddle(runId, 72, 32, 30)} · benchmark={benchmark}
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">updated {formatDateTime(updatedAt)}</Badge>
            <Badge variant="outline">{benchmark}</Badge>
          </div>
        </div>
      </header>

      <Card className="mb-4 rounded-[24px] border-white/80 bg-white/92">
        <CardHeader className="pb-2">
          <CardTitle className="text-xl">Switch Trial</CardTitle>
          <CardDescription>输入 trial key 后在当前页面切换目标 trial。</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 md:flex-row md:items-end">
          <div className="min-w-0 flex-1">
            <Input
              value={trialKeyInput}
              onChange={(event) => setTrialKeyInput(event.target.value)}
              placeholder="task::agent::variant::sample"
              className="h-11 font-[family-name:var(--font-mono)] text-base"
            />
          </div>
          <button
            type="button"
            className={cn(buttonVariants({ variant: "outline" }), "h-11")}
            onClick={() => {
              const next = trialKeyInput.trim();
              const params = new URLSearchParams(searchParams.toString());
              if (next) {
                params.set("trial_key", next);
              } else {
                params.delete("trial_key");
              }
              const query = params.toString();
              router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
            }}
          >
            查看这个 Trial
          </button>
        </CardContent>
      </Card>

      <TrialDetailPanel
        title="Trial Detail"
        trialKey={trialKeyFromUrl}
        detail={(trialDetailQuery.data as Record<string, unknown> | null) || null}
        loading={Boolean(trialKeyFromUrl) && trialDetailQuery.isLoading}
        isError={Boolean(trialKeyFromUrl) && trialDetailQuery.isError}
        onOpenPretask={(trialKey) => {
          const normalized = trialKey.trim();
          if (!normalized) {
            return;
          }
          setDrawerTrialKey(normalized);
          setDrawerOpen(true);
        }}
        onBackToTasks={(trialKey) => {
          router.push(`/runs/${encodeURIComponent(runId)}?tab=tasks&trial_key=${encodeURIComponent(trialKey)}`);
        }}
      />

      <PretaskDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        runId={runId}
        trialKey={drawerTrialKey}
        items={pretaskQuery.data?.items || []}
        loading={pretaskQuery.isLoading}
      />
    </main>
  );
}
