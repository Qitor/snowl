"use client";

import { X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime, truncateMiddle } from "@/lib/utils";

type PretaskDrawerProps = {
  open: boolean;
  onClose: () => void;
  runId: string;
  trialKey: string;
  items: Array<Record<string, unknown>>;
  loading?: boolean;
};

export function PretaskDrawer({
  open,
  onClose,
  runId,
  trialKey,
  items,
  loading = false,
}: PretaskDrawerProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <button className="h-full flex-1 bg-black/35" onClick={onClose} aria-label="close-overlay" />
      <aside className="h-full w-full max-w-[640px] overflow-hidden border-l bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <div className="text-base text-muted-foreground">Pretask Diagnostics</div>
            <div className="mt-0.5 font-[family-name:var(--font-mono)] text-sm text-foreground/90" title={runId}>
              run={truncateMiddle(runId, 58, 26, 24)}
            </div>
            <div className="font-[family-name:var(--font-mono)] text-sm text-foreground/90" title={trialKey}>
              trial={truncateMiddle(trialKey, 58, 26, 24)}
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={onClose}>
            <X className="mr-1 h-3.5 w-3.5" />
            关闭
          </Button>
        </div>

        <div className="h-[calc(100%-82px)] overflow-auto px-5 py-4">
          {loading ? <div className="text-base text-muted-foreground">加载中...</div> : null}
          {!loading && items.length === 0 ? (
            <div className="rounded-md border border-dashed p-4 text-base text-muted-foreground">暂无 pretask 事件。</div>
          ) : null}

          <div className="space-y-4">
            {items.map((item, idx) => {
              const stage = String(item.event || "pretask");
              const status = String(item.status || "unknown");
              const message = String(item.message || "");
              const sourceEvent = String(item.source_event || "");
              const command = String(item.command_text || "");
              const exitCode = item.exit_code;
              const tsMs = Number(item.ts_ms || item.started_at_ms || item.ended_at_ms || 0) || null;
              const attentionSummary =
                status === "failed"
                  ? "Pretask step failed. Check source event and command output."
                  : status === "success"
                    ? "Pretask step completed successfully."
                    : "Pretask step is in progress.";
              return (
                <div key={`${stage}-${idx}`} className="rounded-xl border bg-background/50 p-4">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge
                      variant={status === "failed" ? "danger" : status === "success" ? "success" : "warning"}
                    >
                      {status}
                    </Badge>
                    <span className="text-sm font-semibold text-foreground">{attentionSummary}</span>
                  </div>
                  <div className="space-y-1 text-sm leading-6 text-muted-foreground">
                    <div>
                      stage: <span className="font-[family-name:var(--font-mono)] text-[13px] text-foreground/80">{stage}</span>
                    </div>
                    <div>message: {message || "-"}</div>
                    <div>
                      source event:{" "}
                      <span className="font-[family-name:var(--font-mono)] text-[13px] text-foreground/80">
                        {sourceEvent || "-"}
                      </span>
                    </div>
                    <div>timestamp: {formatDateTime(tsMs)}</div>
                    <div>exit code: {exitCode === undefined ? "-" : String(exitCode)}</div>
                  </div>
                  {command ? (
                    <details className="mt-3">
                      <summary className="cursor-pointer text-sm text-primary/90 hover:text-primary">
                        View command / raw pretask payload
                      </summary>
                      <pre className="mt-2 max-h-[240px] overflow-auto rounded-xl border bg-slate-950 px-3 py-2 font-[family-name:var(--font-mono)] text-[12px] leading-5 text-cyan-100">
                        {command}
                      </pre>
                    </details>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </aside>
    </div>
  );
}
