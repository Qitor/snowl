import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPercent(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function formatDateTime(tsMs: number | null | undefined): string {
  if (!tsMs) {
    return "-";
  }
  const d = new Date(tsMs);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
}

export function formatRelativeFromNow(tsMs: number | null | undefined): string {
  if (!tsMs) {
    return "-";
  }
  const delta = Date.now() - tsMs;
  if (!Number.isFinite(delta)) {
    return "-";
  }
  const abs = Math.abs(delta);
  if (abs < 1_000) {
    return "just now";
  }
  if (abs < 60_000) {
    return `${Math.round(abs / 1_000)}s ${delta >= 0 ? "ago" : "from now"}`;
  }
  if (abs < 3_600_000) {
    return `${Math.round(abs / 60_000)}m ${delta >= 0 ? "ago" : "from now"}`;
  }
  if (abs < 86_400_000) {
    return `${Math.round(abs / 3_600_000)}h ${delta >= 0 ? "ago" : "from now"}`;
  }
  return `${Math.round(abs / 86_400_000)}d ${delta >= 0 ? "ago" : "from now"}`;
}

export function truncateMiddle(value: string | null | undefined, maxLen = 42, head = 18, tail = 14): string {
  const raw = String(value || "").trim();
  if (!raw) {
    return "-";
  }
  if (raw.length <= maxLen) {
    return raw;
  }
  const prefix = raw.slice(0, Math.max(3, head));
  const suffix = raw.slice(-Math.max(3, tail));
  return `${prefix}…${suffix}`;
}

export function makeTrialKey(input: {
  task_id?: string | null;
  agent_id?: string | null;
  variant_id?: string | null;
  sample_id?: string | null;
}): string {
  const task = input.task_id || "-";
  const agent = input.agent_id || "-";
  const variant = input.variant_id || "default";
  const sample = input.sample_id || "-";
  return `${task}::${agent}::${variant}::${sample}`;
}

export function makeIdentityKey(input: {
  agent_id?: string | null;
  variant_id?: string | null;
  model?: string | null;
}): string {
  const agent = String(input.agent_id || "-").trim() || "-";
  const variant = String(input.variant_id || "default").trim() || "default";
  const model = String(input.model || "").trim();
  return `${agent}::${variant}::${model}`;
}

export function makeDisplayId(input: {
  agent_id?: string | null;
  variant_id?: string | null;
  model?: string | null;
}): string {
  const agent = String(input.agent_id || "unknown").trim() || "unknown";
  const variant = String(input.variant_id || "default").trim() || "default";
  const model = String(input.model || "").trim();
  if (variant !== "default") {
    return `${agent} / ${variant}`;
  }
  if (model) {
    return `${agent} / ${model}`;
  }
  return agent;
}
