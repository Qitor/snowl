"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useMemo, useRef } from "react";

import type { RuntimeEvent } from "@/lib/types";
import { cn, truncateMiddle } from "@/lib/utils";

type VirtualLogViewerProps = {
  events: RuntimeEvent[];
};

type LogRow = {
  eventId: string;
  eventKey: string;
  summary: string;
  timestampLabel: string;
  identityLabel: string;
  taskId: string;
  trialKey: string;
  phase: string;
  attention: boolean;
  rawText: string;
  modelInputLabel: string | null;
  modelInputPreview: string | null;
  modelOutputLabel: string | null;
  modelOutputPreview: string | null;
};

const EVENT_SUMMARY_MAP: Record<string, string> = {
  "runtime.trial.start": "Trial started",
  "runtime.trial.finish": "Trial finished",
  "runtime.trial.error": "Trial failed",
  "runtime.scorer.start": "Scoring started",
  "runtime.scorer.finish": "Scoring finished",
  "runtime.model.query.start": "Model request started",
  "runtime.model.query.finish": "Model response received",
  "runtime.model.query.error": "Model request failed",
  "runtime.model.io": "Model I/O captured",
  "runtime.agent.step": "Agent step completed",
  "runtime.env.preflight.download.start": "Pretask download started",
  "runtime.env.preflight.download.progress": "Pretask download in progress",
  "runtime.env.preflight.download.finish": "Pretask download finished",
  "runtime.env.preflight.extract.start": "Pretask extract started",
  "runtime.env.preflight.extract.finish": "Pretask extract finished",
  "runtime.env.preflight.error": "Pretask environment error",
  "pretask.started": "Pretask step started",
  "pretask.success": "Pretask step succeeded",
  "pretask.failed": "Pretask step failed",
  "ui.heartbeat": "Monitor heartbeat",
};

function toTitleCaseWords(value: string): string {
  return value
    .split(" ")
    .filter(Boolean)
    .map((word) => word.slice(0, 1).toUpperCase() + word.slice(1))
    .join(" ");
}

function humanizeEventKey(eventKey: string): string {
  const mapped = EVENT_SUMMARY_MAP[eventKey];
  if (mapped) {
    return mapped;
  }
  const reduced = eventKey
    .replace(/^runtime\./, "")
    .replace(/^pretask\./, "pretask ")
    .replace(/^ui\./, "")
    .replace(/[._]+/g, " ");
  return toTitleCaseWords(reduced);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
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

function toPreviewText(value: unknown, maxLen = 220): string {
  if (!hasDisplayValue(value)) {
    return "-";
  }
  if (typeof value === "string") {
    const compact = value.replace(/\s+/g, " ").trim();
    if (compact.length <= maxLen) {
      return compact;
    }
    return `${compact.slice(0, maxLen - 1)}…`;
  }
  try {
    const compact = JSON.stringify(value);
    if (compact.length <= maxLen) {
      return compact;
    }
    return `${compact.slice(0, maxLen - 1)}…`;
  } catch {
    return "[unserializable payload]";
  }
}

function extractMessageListPreview(value: unknown): string | null {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }
  const parts: string[] = [];
  for (const item of value.slice(0, 2)) {
    const row = asRecord(item);
    if (!row) {
      continue;
    }
    const role = String(row.role || "message").trim();
    const content = row.content;
    if (typeof content === "string" && content.trim()) {
      parts.push(`${role}: ${toPreviewText(content, 120)}`);
      continue;
    }
    if (Array.isArray(content)) {
      const textPart = content.find((entry) => {
        const part = asRecord(entry);
        return typeof part?.text === "string" && part.text.trim();
      });
      const text = asRecord(textPart)?.text;
      if (typeof text === "string" && text.trim()) {
        parts.push(`${role}: ${toPreviewText(text, 120)}`);
      }
    }
  }
  return parts.length > 0 ? parts.join(" | ") : null;
}

function extractModelPreview(value: unknown): string | null {
  if (!hasDisplayValue(value)) {
    return null;
  }
  if (typeof value === "string") {
    return toPreviewText(value, 220);
  }
  const record = asRecord(value);
  if (!record) {
    return toPreviewText(value, 220);
  }
  const directMessages = extractMessageListPreview(record.messages);
  if (directMessages) {
    return directMessages;
  }
  const message = asRecord(record.message);
  const messageContent = message?.content;
  if (typeof messageContent === "string" && messageContent.trim()) {
    return toPreviewText(messageContent, 220);
  }
  const content = record.content;
  if (typeof content === "string" && content.trim()) {
    return toPreviewText(content, 220);
  }
  const toolCalls = Array.isArray(message?.tool_calls) ? message.tool_calls : [];
  if (toolCalls.length > 0) {
    const firstCall = asRecord(toolCalls[0]);
    const fn = asRecord(firstCall?.function);
    const name = String(fn?.name || "tool_call").trim();
    const args = fn?.arguments;
    return hasDisplayValue(args) ? `tool ${name}(${toPreviewText(args, 140)})` : `tool ${name}`;
  }
  return toPreviewText(value, 220);
}

function buildRow(event: RuntimeEvent): LogRow {
  const eventKey = String(event.event || "runtime.event");
  const eventId = String(event.event_id || "");
  const phase = String(event.phase || "").trim();
  const message = String(event.message || "").trim();
  const taskId = String(event.task_id || "").trim();
  const trialKey = String(event.trial_key || "").trim();
  const agentId = String(event.agent_id || "").trim();
  const variantId = String(event.variant_id || "default").trim();
  const model = String(event.model || "").trim();
  const direction = String(event.direction || "").trim().toLowerCase();
  const ts = typeof event.ts_ms === "number" ? new Date(event.ts_ms).toLocaleTimeString() : "--:--:--";
  const identityRaw = [agentId || "-", variantId || "default", model || ""].filter(Boolean).join(" / ");
  const modelInputPreview = extractModelPreview(event.model_input);
  const modelOutputPreview = extractModelPreview(event.model_output);
  const summary =
    message ||
    (eventKey === "runtime.model.io" && direction === "input"
      ? "Model input captured"
      : eventKey === "runtime.model.io" && direction === "output"
        ? "Model output captured"
        : humanizeEventKey(eventKey));
  const lower = `${eventKey} ${message}`.toLowerCase();
  const attention =
    lower.includes("error") ||
    lower.includes("failed") ||
    lower.includes("timeout") ||
    eventKey.startsWith("pretask.") ||
    eventKey === "runtime.trial.error";
  return {
    eventId,
    eventKey,
    summary,
    timestampLabel: ts,
    identityLabel: identityRaw || "-",
    taskId: taskId || "-",
    trialKey,
    phase: phase || "-",
    attention,
    rawText: JSON.stringify(event, null, 2),
    modelInputLabel: modelInputPreview ? "Model input" : null,
    modelInputPreview,
    modelOutputLabel: modelOutputPreview ? "Model output" : null,
    modelOutputPreview,
  };
}

export function VirtualLogViewer({ events }: VirtualLogViewerProps) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const rows = useMemo(() => events.map(buildRow), [events]);

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 116,
    measureElement: (el) => el?.getBoundingClientRect().height ?? 0,
    overscan: 10,
  });

  return (
    <div
      ref={parentRef}
      className="h-[500px] overflow-auto rounded-[24px] border border-slate-900/70 bg-[#09131e] p-3 shadow-inner"
    >
      <div
        style={{
          height: `${rowVirtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {rowVirtualizer.getVirtualItems().map((row) => {
          const item = rows[row.index];
          if (!item) {
            return null;
          }
          return (
            <div
              key={row.key}
              ref={rowVirtualizer.measureElement}
              data-index={row.index}
              className={cn(
                "absolute left-0 top-0 w-full border-b border-slate-800/60 px-3 py-2.5",
                item.attention ? "bg-rose-500/10" : row.index % 2 === 0 ? "bg-slate-950/30" : "bg-slate-900/20",
              )}
              style={{ transform: `translateY(${row.start}px)` }}
            >
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <div className="text-sm font-semibold leading-6 text-slate-100">{item.summary}</div>
                <div className="font-[family-name:var(--font-mono)] text-[13px] text-cyan-200/95">{item.timestampLabel}</div>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[13px] leading-6 text-slate-300/90">
                <span className="rounded-md border border-slate-700/80 bg-slate-900/70 px-2 py-0.5">
                  phase {truncateMiddle(item.phase, 18, 8, 6)}
                </span>
                <span className="rounded-md border border-slate-700/80 bg-slate-900/70 px-2 py-0.5">
                  identity {truncateMiddle(item.identityLabel, 46, 20, 18)}
                </span>
                <span className="rounded-md border border-slate-700/80 bg-slate-900/70 px-2 py-0.5">
                  task {truncateMiddle(item.taskId, 30, 16, 10)}
                </span>
                {item.trialKey ? (
                  <span className="rounded-md border border-slate-700/80 bg-slate-900/70 px-2 py-0.5">
                    trial {truncateMiddle(item.trialKey, 56, 24, 22)}
                  </span>
                ) : null}
              </div>
              <div className="mt-1 text-[13px] leading-6 text-slate-400">
                event key: <span className="font-[family-name:var(--font-mono)] text-slate-300">{item.eventKey}</span>
                {item.eventId ? (
                  <>
                    {" · "}id <span className="font-[family-name:var(--font-mono)] text-slate-300">{truncateMiddle(item.eventId, 26, 12, 10)}</span>
                  </>
                ) : null}
              </div>
              {item.modelInputPreview || item.modelOutputPreview ? (
                <div className="mt-2 grid gap-2">
                  {item.modelInputPreview ? (
                    <div className="rounded-xl border border-cyan-800/60 bg-cyan-950/25 px-3 py-2">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-200/80">
                        {item.modelInputLabel}
                      </div>
                      <div className="mt-1 text-[13px] leading-6 text-cyan-50/95">{item.modelInputPreview}</div>
                    </div>
                  ) : null}
                  {item.modelOutputPreview ? (
                    <div className="rounded-xl border border-emerald-800/60 bg-emerald-950/25 px-3 py-2">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-200/80">
                        {item.modelOutputLabel}
                      </div>
                      <div className="mt-1 text-[13px] leading-6 text-emerald-50/95">{item.modelOutputPreview}</div>
                    </div>
                  ) : null}
                </div>
              ) : null}
              <details className="mt-2">
                <summary className="cursor-pointer text-sm text-cyan-200/90 hover:text-cyan-100">
                  View raw event payload
                </summary>
                <pre className="mt-2 max-h-[220px] overflow-auto rounded-xl border border-slate-700/70 bg-slate-950/80 px-3 py-2 font-[family-name:var(--font-mono)] text-[12px] leading-5 text-cyan-100/90">
                  {item.rawText}
                </pre>
              </details>
            </div>
          );
        })}
      </div>
    </div>
  );
}
