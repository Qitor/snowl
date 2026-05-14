"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Download } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn, truncateMiddle } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

type TraceAction = {
  toolName: string;
  arguments: unknown;
  callId?: string;
};

type TraceObservation = {
  result: unknown;
  isError?: boolean;
};

type TraceStep = {
  step: number;
  thought: string | null;
  action: TraceAction | null;
  observation: TraceObservation | null;
  modelIo: { input?: unknown; output?: unknown; model?: string } | null;
  status: string;
  durationMs: number | null;
  tsMs: number | null;
};

type TraceTimelineProps = {
  detail: Record<string, unknown> | null;
  runId?: string;
  trialKey?: string;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function hasDisplayValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0 && value.trim() !== "null";
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length > 0;
  return true;
}

function toPreviewText(value: unknown, maxLen = 260): string {
  if (!hasDisplayValue(value)) return "-";
  if (typeof value === "string") {
    const compact = value.replace(/\s+/g, " ").trim();
    return compact.length <= maxLen ? compact : `${compact.slice(0, maxLen - 1)}…`;
  }
  try {
    const text = JSON.stringify(value);
    return text.length <= maxLen ? text : `${text.slice(0, maxLen - 1)}…`;
  } catch {
    return "[unserializable]";
  }
}

function toPrettyText(value: unknown): string {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
      try { return JSON.stringify(JSON.parse(trimmed), null, 2); } catch { /* keep raw */ }
    }
    return value.replace(/\\n/g, "\n");
  }
  try { return JSON.stringify(value ?? null, null, 2); } catch { return String(value ?? ""); }
}

function extractThoughtText(modelOutput: unknown): string | null {
  if (!hasDisplayValue(modelOutput)) return null;
  if (typeof modelOutput === "string") return toPreviewText(modelOutput, 560);
  const record = asRecord(modelOutput);
  if (!record) return toPreviewText(modelOutput, 560);
  const message = asRecord(record.message) || record;
  const content = message.content;
  if (typeof content === "string" && content.trim()) return toPreviewText(content, 560);
  // If only tool_calls, no thought text
  const toolCalls = Array.isArray(message.tool_calls) ? message.tool_calls : [];
  if (toolCalls.length > 0 && !content) return null;
  return toPreviewText(modelOutput, 560);
}

function extractToolCalls(modelOutput: unknown): TraceAction[] | null {
  const record = asRecord(modelOutput);
  if (!record) return null;
  const message = asRecord(record.message) || record;
  const toolCalls = Array.isArray(message.tool_calls) ? message.tool_calls : [];
  if (toolCalls.length === 0) return null;
  return toolCalls.map((tc: unknown) => {
    const item = asRecord(tc) || {};
    const fn = asRecord(item.function) || item;
    return {
      toolName: String(fn.name || item.name || "tool_call"),
      arguments: fn.arguments ?? item.arguments ?? {},
      callId: item.id != null ? String(item.id) : undefined,
    };
  });
}

// ---------------------------------------------------------------------------
// buildTraceSteps — data assembly
// ---------------------------------------------------------------------------

export function buildTraceSteps(detail: Record<string, unknown> | null): TraceStep[] {
  if (!detail) return [];

  const modelIoEvents = Array.isArray(detail.model_io_events) ? detail.model_io_events : [];
  const agentStepEvents = Array.isArray(detail.agent_step_events) ? detail.agent_step_events : [];
  const trace = asRecord(detail.trace);
  const traceActions = Array.isArray(trace?.actions) ? trace.actions : [];
  const traceObservations = Array.isArray(trace?.observations) ? trace.observations : [];

  // 1. Group model_io_events by step
  const modelIoByStep = new Map<number, { input?: unknown; output?: unknown; model?: string; direction?: string }>();
  for (const rawEvent of modelIoEvents) {
    const event = asRecord(rawEvent);
    if (!event) continue;
    const step = Number(event.step || 0);
    if (step <= 0) continue;
    const existing = modelIoByStep.get(step) || {};
    const dir = String(event.direction || "").trim().toLowerCase();
    if (dir === "input") {
      existing.input = event.model_input ?? event.request ?? existing.input;
    } else if (dir === "output") {
      existing.output = event.model_output ?? event.response ?? existing.output;
    } else {
      if (!hasDisplayValue(existing.output)) {
        existing.output = event.model_output ?? event.response ?? existing.output;
      }
    }
    const model = String(event.model || "").trim();
    if (model) existing.model = model;
    modelIoByStep.set(step, existing);
  }

  // 2. Group agent_step_events by step
  const agentStepByStep = new Map<number, { status: string; durationMs: number | null; tsMs: number | null }>();
  for (const rawEvent of agentStepEvents) {
    const event = asRecord(rawEvent);
    if (!event) continue;
    const step = Number(event.step || 0);
    if (step <= 0) continue;
    agentStepByStep.set(step, {
      status: String(event.status || "unknown"),
      durationMs: Number(event.duration_ms || 0) || null,
      tsMs: Number(event.ts_ms || event.started_at_ms || event.ended_at_ms || 0) || null,
    });
  }

  // 3. Build step map from model_io (primary source of step numbers)
  const stepMap = new Map<number, TraceStep>();

  for (const [step, io] of modelIoByStep) {
    const output = io.output;
    const thought = extractThoughtText(output);
    const toolCalls = extractToolCalls(output);

    // For the action, prefer tool_calls from model output, fall back to trace.actions by position
    let action: TraceAction | null = null;
    if (toolCalls && toolCalls.length > 0) {
      action = toolCalls[0]; // First tool call per step
    } else if (step <= traceActions.length) {
      const rawAction = asRecord(traceActions[step - 1]);
      if (rawAction) {
        const payload = asRecord(rawAction.payload) || {};
        const toolName = String(payload.tool_name || payload.name || "").trim();
        if (toolName) {
          action = { toolName, arguments: payload.arguments ?? payload.args ?? {} };
        }
      }
    }

    // For the observation, use trace.observations by position
    let observation: TraceObservation | null = null;
    if (step <= traceObservations.length) {
      const rawObs = asRecord(traceObservations[step - 1]);
      if (rawObs) {
        const payload = asRecord(rawObs.payload) || {};
        if (hasDisplayValue(payload.result)) {
          observation = { result: payload.result, isError: String(rawObs.observation_type || "").includes("error") };
        }
      }
    }

    const agentInfo = agentStepByStep.get(step);

    stepMap.set(step, {
      step,
      thought,
      action,
      observation,
      modelIo: io,
      status: agentInfo?.status || "completed",
      durationMs: agentInfo?.durationMs ?? null,
      tsMs: agentInfo?.tsMs ?? null,
    });
  }

  // 4. Add any agent_step_events not covered by model_io (edge case)
  for (const [step, info] of agentStepByStep) {
    if (stepMap.has(step)) continue;
    stepMap.set(step, {
      step,
      thought: null,
      action: step <= traceActions.length ? (() => {
        const rawAction = asRecord(traceActions[step - 1]);
        if (!rawAction) return null;
        const payload = asRecord(rawAction.payload) || {};
        const toolName = String(payload.tool_name || payload.name || "").trim();
        return toolName ? { toolName, arguments: payload.arguments ?? {} } : null;
      })() : null,
      observation: step <= traceObservations.length ? (() => {
        const rawObs = asRecord(traceObservations[step - 1]);
        if (!rawObs) return null;
        const payload = asRecord(rawObs.payload) || {};
        return hasDisplayValue(payload.result) ? { result: payload.result } : null;
      })() : null,
      modelIo: null,
      status: info.status,
      durationMs: info.durationMs,
      tsMs: info.tsMs,
    });
  }

  // 5. If no step-numbered data, fall back to positional indexing from trace
  if (stepMap.size === 0 && (traceActions.length > 0 || traceObservations.length > 0)) {
    const maxLen = Math.max(traceActions.length, traceObservations.length);
    for (let i = 0; i < maxLen; i++) {
      const step = i + 1;
      let action: TraceAction | null = null;
      let observation: TraceObservation | null = null;

      if (i < traceActions.length) {
        const rawAction = asRecord(traceActions[i]);
        if (rawAction) {
          const payload = asRecord(rawAction.payload) || {};
          const toolName = String(payload.tool_name || payload.name || "").trim();
          if (toolName) action = { toolName, arguments: payload.arguments ?? {} };
        }
      }

      if (i < traceObservations.length) {
        const rawObs = asRecord(traceObservations[i]);
        if (rawObs) {
          const payload = asRecord(rawObs.payload) || {};
          if (hasDisplayValue(payload.result)) {
            observation = { result: payload.result };
          }
        }
      }

      stepMap.set(step, {
        step,
        thought: null,
        action,
        observation,
        modelIo: null,
        status: "completed",
        durationMs: null,
        tsMs: null,
      });
    }
  }

  return Array.from(stepMap.values()).sort((a, b) => a.step - b.step);
}

// ---------------------------------------------------------------------------
// Expandable JSON block
// ---------------------------------------------------------------------------

function ExpandableBlock({ label, value, defaultOpen = false }: { label: string; value: unknown; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const text = toPrettyText(value);

  if (!hasDisplayValue(value)) return null;

  return (
    <div className="mt-2">
      <button
        type="button"
        className="flex items-center gap-1 text-xs uppercase tracking-[0.12em] text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {label}
      </button>
      {open ? (
        <pre className="mt-1 max-h-[260px] overflow-auto rounded-lg border bg-slate-950 px-3 py-2 text-[12px] leading-5 whitespace-pre-wrap break-all text-cyan-100">
          {text}
        </pre>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single step row
// ---------------------------------------------------------------------------

function StepCard({ step, isLast }: { step: TraceStep; isLast: boolean }) {
  const hasThought = step.thought !== null && step.thought !== "-";
  const hasAction = step.action !== null;
  const hasObservation = step.observation !== null;
  const hasModelIo = step.modelIo !== null && (hasDisplayValue(step.modelIo.input) || hasDisplayValue(step.modelIo.output));

  return (
    <div className="flex gap-4">
      {/* Timeline connector */}
      <div className="flex flex-col items-center">
        <div className="h-3 w-3 rounded-full bg-primary ring-4 ring-primary/10 shrink-0" />
        {!isLast ? <div className="w-0.5 flex-1 bg-border" /> : null}
      </div>

      {/* Step content */}
      <div className={cn("flex-1 pb-6", !isLast ? "" : "pb-0")}>
        <div className="rounded-[8px] border border-[#ededed] bg-white p-4">
          {/* Step header */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Step {step.step}</span>
            {step.status && step.status !== "completed" && step.status !== "-" ? (
              <Badge variant={step.status === "error" ? "danger" : "outline"}>{step.status}</Badge>
            ) : null}
            {step.durationMs != null && step.durationMs > 0 ? (
              <Badge variant="outline">{step.durationMs}ms</Badge>
            ) : null}
            {step.modelIo?.model ? (
              <Badge variant="outline">{step.modelIo.model}</Badge>
            ) : null}
          </div>

          {/* Thought */}
          {hasThought ? (
            <div className="mt-3">
              <div className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Thought</div>
              <div className="mt-1 text-sm leading-6 text-foreground">{step.thought}</div>
            </div>
          ) : null}

          {/* Action */}
          {hasAction ? (
            <div className="mt-3">
              <div className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Action</div>
              <div className="mt-1 font-mono text-sm text-primary">
                {step.action!.toolName}
                <span className="text-foreground/70">
                  ({toPreviewText(step.action!.arguments, 180)})
                </span>
              </div>
              {hasDisplayValue(step.action!.arguments) ? (
                <ExpandableBlock label="Arguments" value={step.action!.arguments} />
              ) : null}
            </div>
          ) : null}

          {/* Observation */}
          {hasObservation ? (
            <div className="mt-3">
              <div className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Observation</div>
              <div className={cn("mt-1 text-sm leading-6", step.observation!.isError ? "text-danger" : "text-foreground")}>
                {toPreviewText(step.observation!.result, 340)}
              </div>
              {hasDisplayValue(step.observation!.result) ? (
                <ExpandableBlock label="Full result" value={step.observation!.result} />
              ) : null}
            </div>
          ) : null}

          {/* Model IO (collapsed by default) */}
          {hasModelIo ? (
            <div className="mt-2 border-t border-[#ededed] pt-2">
              {hasDisplayValue(step.modelIo!.input) ? (
                <ExpandableBlock label="Model input" value={step.modelIo!.input} />
              ) : null}
              {hasDisplayValue(step.modelIo!.output) ? (
                <ExpandableBlock label="Model output" value={step.modelIo!.output} />
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Final answer node
// ---------------------------------------------------------------------------

function FinalAnswerNode({ finalOutput }: { finalOutput: unknown }) {
  if (!hasDisplayValue(finalOutput)) return null;

  const record = asRecord(finalOutput);
  let text = "-";
  if (typeof finalOutput === "string") {
    text = toPreviewText(finalOutput, 560);
  } else if (record) {
    const message = asRecord(record.message);
    const content = (record.content as string | undefined) || (message?.content as string | undefined);
    text = content ? toPreviewText(content, 560) : toPreviewText(finalOutput, 560);
  }

  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <div className="h-3 w-3 rounded-full bg-foreground ring-4 ring-foreground/10 shrink-0" />
      </div>
      <div className="flex-1 pb-2">
        <div className="rounded-[8px] border border-[#ededed] bg-emerald-50/50 p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-foreground">Final Answer</div>
          <div className="mt-1 text-sm leading-6 text-foreground">{text}</div>
          {hasDisplayValue(finalOutput) ? (
            <ExpandableBlock label="Full output" value={finalOutput} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function TraceTimeline({ detail, runId, trialKey }: TraceTimelineProps) {
  const steps = buildTraceSteps(detail);
  const finalOutput = detail?.final_output;
  const trace = asRecord(detail?.trace);
  const stopReason = String(trace?.stop_reason || "");

  if (steps.length === 0 && !hasDisplayValue(finalOutput)) {
    return (
      <div className="rounded-[8px] border border-dashed p-4 text-sm text-muted-foreground">
        No execution trace available for this trial.
      </div>
    );
  }

  return (
    <div className="space-y-0">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">
          Execution Trace · {steps.length} step{steps.length !== 1 ? "s" : ""}
          {stopReason && stopReason !== "completed" ? ` · stopped: ${stopReason}` : ""}
        </div>
        {runId && trialKey ? (
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#ededed] bg-white px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => {
              const url = `/api/runs/${encodeURIComponent(runId)}/export?format=json&trial_key=${encodeURIComponent(trialKey)}`;
              fetch(url)
                .then((res) => res.blob())
                .then((blob) => {
                  const a = document.createElement("a");
                  a.href = URL.createObjectURL(blob);
                  a.download = `trace_${truncateMiddle(runId, 24, 10, 10)}_${truncateMiddle(trialKey, 32, 14, 12)}.json`;
                  a.click();
                  URL.revokeObjectURL(a.href);
                })
                .catch(() => { /* ignore */ });
            }}
          >
            <Download className="h-3.5 w-3.5" />
            Export
          </button>
        ) : null}
      </div>

      <div>
        {steps.map((step, idx) => (
          <StepCard key={`step-${step.step}`} step={step} isLast={idx === steps.length - 1 && !hasDisplayValue(finalOutput)} />
        ))}
        {hasDisplayValue(finalOutput) ? <FinalAnswerNode finalOutput={finalOutput} /> : null}
      </div>
    </div>
  );
}
