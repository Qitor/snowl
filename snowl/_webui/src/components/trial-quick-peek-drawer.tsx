"use client";

import { X } from "lucide-react";
import { buildTraceSteps } from "@/components/trace-timeline";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { truncateMiddle } from "@/lib/utils";

type TrialQuickPeekDrawerProps = {
  open: boolean;
  onClose: () => void;
  runId: string;
  trialKey: string;
  detail: Record<string, unknown> | null;
  loading?: boolean;
  onOpenDetailPage: (trialKey: string) => void;
  onOpenWorkspaceDetail: (trialKey: string) => void;
};

function hasDisplayValue(value: unknown): boolean {
  if (value === null || value === undefined) {
    return false;
  }
  if (typeof value === "string") {
    return value.trim().length > 0 && value.trim().toLowerCase() !== "null";
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.keys(value as Record<string, unknown>).length > 0;
  }
  return true;
}

function previewText(value: unknown, maxLen = 420): string {
  if (!hasDisplayValue(value)) {
    return "-";
  }
  if (typeof value === "string") {
    const text = value.replace(/\s+/g, " ").trim();
    if (text.length <= maxLen) {
      return text;
    }
    return `${text.slice(0, maxLen - 1)}…`;
  }
  try {
    const text = JSON.stringify(value);
    if (text.length <= maxLen) {
      return text;
    }
    return `${text.slice(0, maxLen - 1)}…`;
  } catch {
    return "[unserializable payload]";
  }
}

function prettyText(value: unknown): string {
  if (typeof value === "string") {
    const text = value.trim();
    if ((text.startsWith("{") && text.endsWith("}")) || (text.startsWith("[") && text.endsWith("]"))) {
      try {
        return JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        return value;
      }
    }
    return value;
  }
  try {
    return JSON.stringify(value ?? null, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

export function TrialQuickPeekDrawer({
  open,
  onClose,
  runId,
  trialKey,
  detail,
  loading = false,
  onOpenDetailPage,
  onOpenWorkspaceDetail,
}: TrialQuickPeekDrawerProps) {
  if (!open) {
    return null;
  }

  const finalOutput = asRecord(detail?.final_output || null);
  const errorPayload = detail?.error || detail?.error_event || null;
  const status = String(detail?.status || "unknown").toLowerCase();
  const outputPreview = previewText(
    (finalOutput?.content as string | undefined) ||
      ((asRecord(finalOutput?.message)?.content as string | undefined) ?? null) ||
      finalOutput,
    500,
  );
  const errorPreview = previewText(errorPayload, 500);

  return (
    <div className="fixed inset-0 z-50 flex">
      <button className="h-full flex-1 bg-black/35" onClick={onClose} aria-label="close-overlay" />
      <aside className="h-full w-full max-w-[760px] overflow-hidden border-l bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <div className="text-base text-muted-foreground">Quick Result / Error Peek</div>
            <div className="mt-0.5 font-[family-name:var(--font-mono)] text-sm text-foreground/90" title={runId}>
              run={truncateMiddle(runId, 64, 28, 26)}
            </div>
            <div className="font-[family-name:var(--font-mono)] text-sm text-foreground/90" title={trialKey}>
              trial={truncateMiddle(trialKey, 64, 28, 26)}
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={onClose}>
            <X className="mr-1 h-3.5 w-3.5" />
            Close
          </Button>
        </div>

        <div className="h-[calc(100%-82px)] overflow-auto px-5 py-4">
          {loading ? <div className="text-base text-muted-foreground">Loading...</div> : null}
          {!loading && !detail ? (
            <div className="rounded-md border border-dashed p-4 text-base text-muted-foreground">No trial detail available.</div>
          ) : null}

          {!loading && detail ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-background/60 p-3">
                <Badge variant={status === "success" ? "success" : status === "error" ? "danger" : "warning"}>
                  {status}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {status === "error" ? "This trial ended with error diagnostics." : "Latest result snapshot from this trial."}
                </span>
              </div>

              <div className="rounded-xl border bg-background/60 p-4">
                <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">Last result summary</div>
                <div className="mt-2 text-sm leading-6 text-foreground">{outputPreview}</div>
              </div>

              <TraceSummary detail={detail} />

              <div
                className={`rounded-xl border p-4 ${
                  hasDisplayValue(errorPayload) ? "border-rose-300 bg-rose-50/80" : "border-emerald-300 bg-emerald-50/70"
                }`}
              >
                <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">Error diagnostics</div>
                <div className="mt-2 text-sm leading-6 text-foreground">
                  {hasDisplayValue(errorPayload) ? errorPreview : "No explicit error payload on this trial."}
                </div>
              </div>

              <div className="grid gap-2 md:grid-cols-2">
                <Button
                  variant="outline"
                  className="h-11"
                  onClick={() => {
                    onOpenDetailPage(trialKey);
                    onClose();
                  }}
                >
                  Open Trial Detail page
                </Button>
                <Button
                  variant="default"
                  className="h-11"
                  onClick={() => {
                    onOpenWorkspaceDetail(trialKey);
                    onClose();
                  }}
                >
                  Open Trial Detail in Workspace
                </Button>
              </div>

              <details className="rounded-xl border bg-background/60 px-3 py-2">
                <summary className="cursor-pointer text-sm font-medium text-foreground">View full raw result / error</summary>
                <div className="mt-2 grid gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-[0.12em] text-muted-foreground">final_output</div>
                    <pre className="mt-1 max-h-[260px] overflow-auto rounded-xl border bg-slate-950 px-3 py-2 text-[12px] leading-5 whitespace-pre-wrap break-all text-cyan-100">
                      {prettyText(detail.final_output)}
                    </pre>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-[0.12em] text-muted-foreground">error / error_event</div>
                    <pre className="mt-1 max-h-[260px] overflow-auto rounded-xl border bg-slate-950 px-3 py-2 text-[12px] leading-5 whitespace-pre-wrap break-all text-cyan-100">
                      {prettyText(errorPayload)}
                    </pre>
                  </div>
                </div>
              </details>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function TraceSummary({ detail }: { detail: Record<string, unknown> | null }) {
  const steps = buildTraceSteps(detail);
  if (steps.length === 0) return null;

  return (
    <div className="rounded-xl border border-[#ededed] bg-white p-4">
      <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">
        Trace Summary · {steps.length} step{steps.length !== 1 ? "s" : ""}
      </div>
      <div className="mt-2 space-y-1.5">
        {steps.map((step) => (
          <div key={step.step} className="flex items-start gap-2 text-sm">
            <span className="shrink-0 font-mono text-xs text-primary">{step.step}.</span>
            {step.action ? (
              <span className="font-mono text-primary">
                {step.action.toolName}
                <span className="text-foreground/70">({previewText(step.action.arguments, 60)})</span>
              </span>
            ) : step.thought ? (
              <span className="text-muted-foreground">{previewText(step.thought, 100)}</span>
            ) : null}
            {step.observation ? (
              <span className="text-muted-foreground">→ {previewText(step.observation.result, 80)}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
