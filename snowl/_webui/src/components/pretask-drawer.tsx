"use client";

import { X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

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
        <div className="flex items-center justify-between border-b px-5 py-3">
          <div>
            <div className="text-sm text-muted-foreground">Pretask 诊断</div>
            <div className="font-[family-name:var(--font-mono)] text-xs">run={runId}</div>
            <div className="font-[family-name:var(--font-mono)] text-xs">trial={trialKey}</div>
          </div>
          <Button size="sm" variant="outline" onClick={onClose}>
            <X className="mr-1 h-3.5 w-3.5" />
            关闭
          </Button>
        </div>

        <div className="h-[calc(100%-82px)] overflow-auto px-5 py-4">
          {loading ? <div className="text-sm text-muted-foreground">加载中...</div> : null}
          {!loading && items.length === 0 ? (
            <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">暂无 pretask 事件。</div>
          ) : null}

          <div className="space-y-3">
            {items.map((item, idx) => {
              const stage = String(item.event || "pretask");
              const status = String(item.status || "unknown");
              const message = String(item.message || "");
              const sourceEvent = String(item.source_event || "");
              const command = String(item.command_text || "");
              const exitCode = item.exit_code;
              return (
                <div key={`${stage}-${idx}`} className="rounded-lg border bg-background/40 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <Badge
                      variant={status === "failed" ? "danger" : status === "success" ? "success" : "warning"}
                    >
                      {status}
                    </Badge>
                    <span className="font-[family-name:var(--font-mono)] text-xs">{stage}</span>
                  </div>
                  <div className="space-y-1 text-xs text-muted-foreground">
                    <div>message: {message || "-"}</div>
                    <div>source: {sourceEvent || "-"}</div>
                    <div>exit_code: {exitCode === undefined ? "-" : String(exitCode)}</div>
                    {command ? (
                      <pre className="overflow-x-auto rounded border bg-slate-950 px-2 py-1 font-[family-name:var(--font-mono)] text-[11px] text-cyan-100">
                        {command}
                      </pre>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </aside>
    </div>
  );
}
