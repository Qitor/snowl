"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { TrialAttemptRow } from "@/lib/types";
import { cn, formatDateTime, formatRelativeFromNow, truncateMiddle } from "@/lib/utils";

type AgentStepView = {
  step: number;
  thought: string;
  action: string;
  observation: string;
  mode: string;
  status: string;
  message: string;
};

type TrialDetailPanelProps = {
  trialKey: string;
  detail: Record<string, unknown> | null;
  loading?: boolean;
  isError?: boolean;
  onOpenPretask?: (trialKey: string) => void;
  onBackToTasks?: (trialKey: string) => void;
  title?: string;
};

function toPrettyText(value: unknown): string {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        return JSON.stringify(JSON.parse(trimmed), null, 2);
      } catch {
        // keep raw text when parsing fails
      }
    }
    return value.replace(/\\n/g, "\n");
  }
  try {
    return JSON.stringify(value ?? null, null, 2);
  } catch {
    return String(value ?? "");
  }
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

function toPreviewText(value: unknown, maxLen = 260): string {
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
  if (typeof value === "object") {
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
  return String(value);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function inferTrialPhase(input: {
  status: string;
  startEvent?: Record<string, unknown> | null;
  finishEvent?: Record<string, unknown> | null;
  errorEvent?: Record<string, unknown> | null;
}): string {
  const status = input.status.toLowerCase();
  if (input.errorEvent || status === "error") {
    return "failed";
  }
  if (input.finishEvent || status === "success") {
    return "completed";
  }
  if (status === "scoring") {
    return "scoring";
  }
  if (input.startEvent || status === "running") {
    return "running";
  }
  if (status === "queued") {
    return "queued";
  }
  return status || "unknown";
}

function extractQuestionText(sampleInput: unknown): string {
  if (!hasDisplayValue(sampleInput)) {
    return "-";
  }
  if (typeof sampleInput === "string") {
    return toPreviewText(sampleInput, 560);
  }
  const record = asRecord(sampleInput);
  if (!record) {
    return toPreviewText(sampleInput, 560);
  }
  const candidateKeys = ["question", "query", "prompt", "instruction", "input", "problem", "user_input", "text"];
  for (const key of candidateKeys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return toPreviewText(value, 560);
    }
  }
  const messages = Array.isArray(record.messages) ? record.messages : [];
  for (const message of messages) {
    const msg = asRecord(message);
    if (!msg) {
      continue;
    }
    const role = String(msg.role || "").toLowerCase();
    const content = msg.content;
    if ((role === "user" || role === "question") && typeof content === "string" && content.trim()) {
      return toPreviewText(content, 560);
    }
  }
  return toPreviewText(sampleInput, 560);
}

function extractAnswerText(finalOutput: unknown): string {
  if (!hasDisplayValue(finalOutput)) {
    return "-";
  }
  if (typeof finalOutput === "string") {
    return toPreviewText(finalOutput, 560);
  }
  const record = asRecord(finalOutput);
  if (!record) {
    return toPreviewText(finalOutput, 560);
  }
  const message = asRecord(record.message);
  const candidates = [record.content, message?.content, record.answer, record.output, record.response];
  for (const value of candidates) {
    if (typeof value === "string" && value.trim()) {
      return toPreviewText(value, 560);
    }
  }
  return toPreviewText(finalOutput, 560);
}

function summarizeTraceAction(action: unknown): string {
  const row = asRecord(action);
  if (!row) {
    return toPreviewText(action, 360);
  }
  const payload = asRecord(row.payload);
  const actionType = String(row.action_type || payload?.type || "action").trim();
  const toolName = String(payload?.tool_name || payload?.name || "").trim();
  const rawArgs = payload?.arguments ?? payload?.args ?? payload?.input ?? null;
  const argsText = hasDisplayValue(rawArgs) ? toPreviewText(rawArgs, 220) : "";
  if (toolName) {
    return argsText ? `${actionType} ${toolName}(${argsText})` : `${actionType} ${toolName}`;
  }
  return argsText ? `${actionType} ${argsText}` : toPreviewText(action, 360);
}

function summarizeTraceObservation(observation: unknown): string {
  const row = asRecord(observation);
  if (!row) {
    return toPreviewText(observation, 360);
  }
  const payload = asRecord(row.payload);
  const observationType = String(row.observation_type || payload?.type || "observation").trim();
  const result = payload?.result ?? payload?.observation ?? payload?.content ?? null;
  const resultText = hasDisplayValue(result) ? toPreviewText(result, 280) : "";
  return resultText ? `${observationType}: ${resultText}` : toPreviewText(observation, 360);
}

function buildAgentStepViews(detail: Record<string, unknown> | null): AgentStepView[] {
  if (!detail) {
    return [];
  }
  const stepMap = new Map<number, AgentStepView>();
  const ensureStep = (step: number): AgentStepView => {
    const normalizedStep = Math.max(1, Number.isFinite(step) ? Math.floor(step) : 1);
    if (!stepMap.has(normalizedStep)) {
      stepMap.set(normalizedStep, {
        step: normalizedStep,
        thought: "-",
        action: "-",
        observation: "-",
        mode: "-",
        status: "-",
        message: "-",
      });
    }
    return stepMap.get(normalizedStep) as AgentStepView;
  };

  const trace = asRecord(detail.trace);
  const traceActions = Array.isArray(trace?.actions) ? trace.actions : [];
  for (let i = 0; i < traceActions.length; i += 1) {
    const row = ensureStep(i + 1);
    row.action = summarizeTraceAction(traceActions[i]);
  }

  const traceObservations = Array.isArray(trace?.observations) ? trace.observations : [];
  for (let i = 0; i < traceObservations.length; i += 1) {
    const row = ensureStep(i + 1);
    row.observation = summarizeTraceObservation(traceObservations[i]);
  }

  const traceEvents = Array.isArray(trace?.trace_events) ? trace.trace_events : [];
  for (let i = 0; i < traceEvents.length; i += 1) {
    const event = asRecord(traceEvents[i]);
    if (!event) {
      continue;
    }
    const stepCandidate = Number(event.step || 0);
    const step = Number.isFinite(stepCandidate) && stepCandidate > 0 ? stepCandidate : i + 1;
    const row = ensureStep(step);
    const message = event.message;
    if (typeof message === "string" && message.trim() && row.message === "-") {
      row.message = toPreviewText(message, 260);
    }
  }

  const modelIoEvents = Array.isArray(detail.model_io_events) ? detail.model_io_events : [];
  for (let i = 0; i < modelIoEvents.length; i += 1) {
    const event = asRecord(modelIoEvents[i]);
    if (!event) {
      continue;
    }
    const stepCandidate = Number(event.step || 0);
    const step = Number.isFinite(stepCandidate) && stepCandidate > 0 ? stepCandidate : i + 1;
    const row = ensureStep(step);
    const mode = String(event.mode || "").trim();
    if (mode && row.mode === "-") {
      row.mode = mode;
    }

    const response = asRecord(event.response);
    const message = asRecord(response?.message);
    const thought = message?.content;
    if (typeof thought === "string" && thought.trim()) {
      row.thought = toPreviewText(thought, 560);
    }
    const toolCalls = Array.isArray(message?.tool_calls) ? message.tool_calls : [];
    if (toolCalls.length > 0 && row.action === "-") {
      const firstCall = asRecord(toolCalls[0]);
      const fn = asRecord(firstCall?.function);
      const name = String(fn?.name || "tool_call");
      const args = fn?.arguments;
      row.action = hasDisplayValue(args) ? `tool_call ${name}(${toPreviewText(args, 220)})` : `tool_call ${name}`;
    }
  }

  const agentStepEvents = Array.isArray(detail.agent_step_events) ? detail.agent_step_events : [];
  for (let i = 0; i < agentStepEvents.length; i += 1) {
    const event = asRecord(agentStepEvents[i]);
    if (!event) {
      continue;
    }
    const stepCandidate = Number(event.step || 0);
    const step = Number.isFinite(stepCandidate) && stepCandidate > 0 ? stepCandidate : i + 1;
    const row = ensureStep(step);
    const status = String(event.status || "").trim();
    const mode = String(event.mode || "").trim();
    const message = String(event.message || "").trim();
    if (status) {
      row.status = status;
    }
    if (mode) {
      row.mode = mode;
    }
    if (message && row.message === "-") {
      row.message = toPreviewText(message, 260);
    }
  }

  return Array.from(stepMap.values()).sort((lhs, rhs) => lhs.step - rhs.step);
}

export function TrialDetailPanel({
  trialKey,
  detail,
  loading = false,
  isError = false,
  onOpenPretask,
  onBackToTasks,
  title = "Trial Detail",
}: TrialDetailPanelProps) {
  const trialScores = ((detail?.scores as Record<string, unknown> | undefined) || {}) as Record<string, unknown>;
  const trialStatus = String((detail?.status as string | undefined) || "");
  const trialStartEvent = ((detail?.start_event as Record<string, unknown> | undefined) || null) as
    | Record<string, unknown>
    | null;
  const trialFinishEvent = ((detail?.finish_event as Record<string, unknown> | undefined) || null) as
    | Record<string, unknown>
    | null;
  const trialErrorEvent = ((detail?.error_event as Record<string, unknown> | undefined) || null) as
    | Record<string, unknown>
    | null;
  const trialStatusLower = trialStatus.toLowerCase();
  const trialPhase = inferTrialPhase({
    status: trialStatusLower,
    startEvent: trialStartEvent,
    finishEvent: trialFinishEvent,
    errorEvent: trialErrorEvent,
  });
  const trialStartedAtMs = Number(trialStartEvent?.ts_ms || 0) || null;
  const trialFinishedAtMs = Number(trialFinishEvent?.ts_ms || 0) || null;
  const trialErroredAtMs = Number(trialErrorEvent?.ts_ms || 0) || null;
  const trialLastProgressTsMs = trialFinishedAtMs || trialErroredAtMs || trialStartedAtMs || null;
  const trialDurationMs =
    trialStartedAtMs != null && trialLastProgressTsMs != null ? Math.max(0, trialLastProgressTsMs - trialStartedAtMs) : null;
  const runningTooLong =
    (trialPhase === "running" || trialPhase === "scoring") &&
    trialStartedAtMs != null &&
    Date.now() - trialStartedAtMs >= 45_000;
  const attentionReason =
    trialStatusLower === "error"
      ? "Trial ended with an error."
      : runningTooLong
        ? "No recent progress during active execution."
        : trialStatusLower === "queued"
          ? "Trial is still queued and has not started."
          : "No blocking attention signal.";
  const whyItMatters =
    trialStatusLower === "error"
      ? "This trial will stay non-success until the underlying failure cause is resolved."
      : runningTooLong
        ? "Long-running active phases usually indicate environment/pretask/model stalls."
        : trialStatusLower === "queued"
          ? "Queue delay can hide scheduler or resource saturation issues."
          : "Current state looks healthy.";
  const suggestedNextAction =
    trialStatusLower === "error"
      ? "Open Pretask first, then inspect Error Diagnostics and Runtime Logs for this trial."
      : runningTooLong
        ? "Inspect Runtime Logs filtered by this trial key, then open Pretask for the latest stage."
        : trialStatusLower === "queued"
          ? "Inspect Runtime Logs around scheduler dispatch and running trial limits."
          : "Inspect Score Breakdown and Attempt History for quality verification.";
  const finalOutputObject = ((detail?.final_output as Record<string, unknown> | undefined) || {}) as Record<
    string,
    unknown
  >;
  const finalOutputPreview = toPreviewText(
    (finalOutputObject.content as string | undefined) ||
      ((finalOutputObject.message as Record<string, unknown> | undefined)?.content as string | undefined) ||
      finalOutputObject,
    280,
  );
  const sampleInputPreview = toPreviewText(detail?.sample_input, 280);
  const qaQuestionPreview = extractQuestionText(detail?.sample_input);
  const qaAnswerPreview = extractAnswerText(detail?.final_output);
  const hasQaPreview = qaQuestionPreview !== "-" || qaAnswerPreview !== "-";
  const agentStepViews = buildAgentStepViews(detail);
  const attemptHistory = Array.isArray(detail?.attempt_history) ? (detail?.attempt_history as TrialAttemptRow[]) : [];
  const rawTrialSections = [
    { key: "payload", title: "Task Payload", value: detail?.sample_input },
    { key: "result", title: "Result Artifact", value: detail?.final_output },
    { key: "trace", title: "Execution Trace", value: detail?.trace },
    { key: "start", title: "Runtime Start Event", value: detail?.start_event },
    { key: "finish", title: "Runtime Finish Event", value: detail?.finish_event },
    { key: "error", title: "Error Diagnostics", value: detail?.error ?? detail?.error_event },
  ].filter((section) => hasDisplayValue(section.value));

  return (
    <Card className="rounded-[28px] border-white/80 bg-white/92 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="text-3xl tracking-tight">{title}</CardTitle>
            <CardDescription className="font-[family-name:var(--font-mono)] text-sm text-muted-foreground" title={trialKey}>
              {trialKey ? `trial=${truncateMiddle(trialKey, 76, 32, 30)}` : "从任务列表或日志中选择一个 trial 查看细节"}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {onBackToTasks && trialKey ? (
              <Button size="sm" variant="outline" onClick={() => onBackToTasks(trialKey)}>
                返回 Tasks
              </Button>
            ) : null}
            {onOpenPretask ? (
              <Button size="sm" variant="outline" onClick={() => onOpenPretask(trialKey)} disabled={!trialKey}>
                打开 Pretask
              </Button>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {!trialKey ? (
          <div className="rounded-md border border-dashed p-4 text-base text-muted-foreground">
            在 Tasks 里点击“查看详情”，或在 Runtime Logs 输入 trial key。
          </div>
        ) : null}
        {trialKey && loading ? <div className="text-base text-muted-foreground">加载详情中...</div> : null}
        {trialKey && isError ? (
          <div className="rounded-md border border-dashed p-4 text-base text-danger">加载详情失败，请重试。</div>
        ) : null}
        {trialKey && !loading && !isError && !detail ? (
          <div className="rounded-md border border-dashed p-4 text-base text-muted-foreground">
            没找到这个 trial 的可用详情。请检查 trial key，或回到 Tasks 清空过滤后重新选择。
          </div>
        ) : null}
        {trialKey && !loading && !isError && detail ? (
          <>
            <div className="space-y-3 rounded-[24px] border bg-muted/15 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={trialStatusLower === "success" ? "success" : trialStatusLower === "error" ? "danger" : "warning"}>
                  {trialStatus || "unknown"}
                </Badge>
                <Badge variant="outline">phase {trialPhase}</Badge>
                {trialDurationMs != null ? <Badge variant="outline">duration {trialDurationMs}ms</Badge> : null}
                {detail?.attempt_no ? <Badge variant="outline">attempt {String(detail.attempt_no)}</Badge> : null}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-2xl border bg-background p-3">
                  <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">Current phase</div>
                  <div className="mt-1 text-lg font-semibold text-foreground">{trialPhase}</div>
                </div>
                <div className="rounded-2xl border bg-background p-3">
                  <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">Last meaningful progress</div>
                  <div className="mt-1 text-lg font-semibold text-foreground">{formatRelativeFromNow(trialLastProgressTsMs)}</div>
                  <div className="text-sm text-muted-foreground">{formatDateTime(trialLastProgressTsMs)}</div>
                </div>
              </div>
              <div
                className={cn(
                  "rounded-2xl border p-3",
                  trialStatusLower === "error" || runningTooLong || trialStatusLower === "queued"
                    ? "border-amber-300 bg-amber-50/70"
                    : "border-emerald-300 bg-emerald-50/70",
                )}
              >
                <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">Attention summary</div>
                <div className="mt-1 text-base font-semibold text-foreground">{attentionReason}</div>
                <div className="mt-1 text-sm text-muted-foreground">Why it matters: {whyItMatters}</div>
                <div className="mt-1 text-sm text-muted-foreground">Next step: {suggestedNextAction}</div>
              </div>
            </div>

            <div className="space-y-3 rounded-[24px] border bg-muted/15 p-4">
              <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">Structured detail</div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-2xl border bg-background p-3">
                  <div className="text-sm font-medium text-muted-foreground">Task / Agent / Variant</div>
                  <div className="mt-2 space-y-1 text-[13px] text-muted-foreground">
                    <div title={String((detail?.task_id as string | undefined) || "-")}>
                      task {truncateMiddle(String((detail?.task_id as string | undefined) || "-"), 42, 18, 16)}
                    </div>
                    <div title={String((detail?.agent_id as string | undefined) || "-")}>
                      agent {truncateMiddle(String((detail?.agent_id as string | undefined) || "-"), 42, 18, 16)}
                    </div>
                    <div title={String((detail?.variant_id as string | undefined) || "default")}>
                      variant {truncateMiddle(String((detail?.variant_id as string | undefined) || "default"), 42, 18, 16)}
                    </div>
                    <div title={String((detail?.sample_id as string | undefined) || "-")}>
                      sample {truncateMiddle(String((detail?.sample_id as string | undefined) || "-"), 42, 18, 16)}
                    </div>
                  </div>
                </div>
                <div className="rounded-2xl border bg-background p-3">
                  <div className="text-sm font-medium text-muted-foreground">Last meaningful output</div>
                  <div className="mt-2 text-sm leading-6 text-foreground">{finalOutputPreview}</div>
                </div>
                <div className="rounded-2xl border bg-background p-3 md:col-span-2">
                  <div className="text-sm font-medium text-muted-foreground">Sample input preview</div>
                  <div className="mt-2 text-sm leading-6 text-foreground">{sampleInputPreview}</div>
                </div>
                {hasQaPreview ? (
                  <div className="rounded-2xl border bg-background p-3 md:col-span-2">
                    <div className="text-sm font-medium text-muted-foreground">QA Preview</div>
                    <div className="mt-2 grid gap-2">
                      <div>
                        <div className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Question</div>
                        <div className="mt-1 text-sm leading-6 text-foreground">{qaQuestionPreview}</div>
                      </div>
                      <div>
                        <div className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Answer</div>
                        <div className="mt-1 text-sm leading-6 text-foreground">{qaAnswerPreview}</div>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            {agentStepViews.length > 0 ? (
              <div className="space-y-2 rounded-[24px] border bg-muted/15 p-4">
                <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">Agent steps (thought / action / observation)</div>
                <div className="grid gap-2">
                  {agentStepViews.map((step) => (
                    <div key={`step-${step.step}`} className="rounded-2xl border bg-background p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline">step {step.step}</Badge>
                        {step.mode !== "-" ? <Badge variant="outline">mode {step.mode}</Badge> : null}
                        {step.status !== "-" ? <Badge variant={step.status === "completed" ? "success" : "outline"}>{step.status}</Badge> : null}
                      </div>
                      {step.message !== "-" ? <div className="mt-1 text-sm text-muted-foreground">{step.message}</div> : null}
                      <div className="mt-2 grid gap-2">
                        <div>
                          <div className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Thought</div>
                          <div className="mt-1 text-sm leading-6 text-foreground">{step.thought}</div>
                        </div>
                        <div>
                          <div className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Action</div>
                          <div className="mt-1 font-[family-name:var(--font-mono)] text-[13px] leading-6 text-foreground">{step.action}</div>
                        </div>
                        <div>
                          <div className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Observation</div>
                          <div className="mt-1 text-sm leading-6 text-foreground">{step.observation}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {Object.keys(trialScores).length > 0 ? (
              <div className="space-y-2 rounded-[24px] border bg-muted/15 p-4">
                <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">Score breakdown</div>
                <div className="grid gap-2 md:grid-cols-2">
                  {Object.entries(trialScores).map(([key, value]) => (
                    <div key={key} className="rounded-2xl border bg-background p-3">
                      <div className="font-[family-name:var(--font-mono)] text-sm font-semibold">{key}</div>
                      <pre className="mt-1 max-h-[180px] overflow-auto rounded-xl border bg-slate-950 px-3 py-2 text-sm leading-6 whitespace-pre-wrap break-all text-cyan-100">
                        {toPrettyText(value)}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {attemptHistory.length > 0 ? (
              <div className="space-y-2 rounded-[24px] border bg-muted/15 p-4">
                <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">Attempt history</div>
                <div className="grid gap-2">
                  {attemptHistory.map((attempt) => (
                    <div key={String(attempt.attempt_id || attempt.attempt_no || "attempt")} className="rounded-2xl border bg-background p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={attempt.effective ? "success" : "outline"}>{attempt.effective ? "effective" : "superseded"}</Badge>
                        <span className="text-sm text-muted-foreground">attempt {String(attempt.attempt_no || "-")}</span>
                        <span className="text-sm text-muted-foreground">{String(attempt.status || "unknown")}</span>
                        {attempt.failure_class ? <Badge variant="outline">{attempt.failure_class}</Badge> : null}
                        {attempt.retry_source ? <Badge variant="outline">{attempt.retry_source}</Badge> : null}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                        <span>started={formatDateTime(attempt.started_ts_ms || null)}</span>
                        <span>ended={formatDateTime(attempt.ended_ts_ms || null)}</span>
                        <span>duration={attempt.duration_ms == null ? "-" : `${attempt.duration_ms}ms`}</span>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
                        <span title={String(attempt.supersedes_attempt_id || "-")}>
                          supersedes={truncateMiddle(String(attempt.supersedes_attempt_id || "-"), 36, 14, 12)}
                        </span>
                        <span title={String(attempt.superseded_by_attempt_id || "-")}>
                          superseded_by={truncateMiddle(String(attempt.superseded_by_attempt_id || "-"), 36, 14, 12)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="space-y-2 rounded-[24px] border bg-muted/10 p-4">
              <div className="text-sm uppercase tracking-[0.14em] text-muted-foreground">Raw technical detail</div>
              <div className="text-sm text-muted-foreground">Summary and structured fields are shown above. Expand below only when debugging payload internals.</div>
              {rawTrialSections.length === 0 ? (
                <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">暂无可展示字段。</div>
              ) : (
                rawTrialSections.map((section) => (
                  <details key={section.key} className="rounded-xl border bg-background px-3 py-2">
                    <summary className="cursor-pointer text-sm font-medium text-foreground">{section.title}</summary>
                    <pre className="mt-2 max-h-[320px] overflow-auto rounded-xl border bg-slate-950 px-3 py-2 text-[12px] leading-6 whitespace-pre-wrap break-all text-cyan-100">
                      {toPrettyText(section.value)}
                    </pre>
                  </details>
                ))
              )}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
