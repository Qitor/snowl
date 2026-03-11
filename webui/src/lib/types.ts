export type ExperimentRow = {
  experiment_id: string;
  run_count: number;
  running: number;
  completed: number;
  updated_at_ms: number;
  benchmarks: string[];
};

export type RunRow = {
  run_id: string;
  experiment_id: string;
  benchmark: string;
  status: "running" | "completed" | "cancelled" | "zombie";
  status_reason: string;
  done: number;
  total: number;
  failed: number;
  updated_at_ms: number;
  path: string;
  variant_count: number;
  models: string[];
  is_live: boolean;
  stalled: boolean;
  attention_count: number;
  has_task_monitor: boolean;
  heartbeat_only: boolean;
  last_progress_ts_ms: number | null;
  runner_alive: boolean;
  observer_stale: boolean;
  recoverable_trials?: number;
  retried_trials?: number;
  recovered_trials?: number;
  still_failing_trials?: number;
  unfinished_trials?: number;
};

export type RunSnapshot = {
  run_id: string;
  experiment_id: string;
  benchmark: string;
  status: "running" | "completed" | "cancelled" | "zombie";
  status_reason: string;
  done: number;
  total: number;
  failed: number;
  summary: Record<string, unknown>;
  plan: Record<string, unknown>;
  task_monitor: Array<Record<string, unknown>>;
  controls?: Record<string, unknown>;
  updated_at_ms: number;
  last_event_id: string | null;
  path?: string;
  variant_count: number;
  models: string[];
  planned_trials: number;
  planned_tasks: number;
  visible_task_rows: number;
  scored_trials: number;
  retry_attempts?: number;
  recovered_count?: number;
  outstanding_failures?: number;
  recoverable_trials?: number;
  retried_trials?: number;
  recovered_trials?: number;
  still_failing_trials?: number;
  unfinished_trials?: number;
  attention_task_count: number;
  last_progress_ts_ms: number | null;
  last_metric_ts_ms: number | null;
  stalled: boolean;
  heartbeat_only: boolean;
  runner_alive: boolean;
  observer_stale: boolean;
  identities: Array<{
    display_id: string;
    agent_id: string;
    variant_id: string;
    model: string | null;
  }>;
};

export type IdentitySummaryRow = {
  display_id: string;
  agent_id: string;
  variant_id: string;
  model: string | null;
  metrics: Record<string, number>;
  rank_score: number;
  count?: number;
  status_counts?: Record<string, number>;
  scored_trials?: number;
  metric_counts?: Record<string, number>;
};

export type RunSummaryResponse = {
  run_id: string;
  experiment_id: string;
  benchmark: string;
  status: "running" | "completed" | "cancelled" | "zombie";
  primary_dimension: "variant-first" | "benchmark-first";
  variant_count: number;
  models: string[];
  identities: Array<{
    display_id: string;
    agent_id: string;
    variant_id: string;
    model: string | null;
  }>;
  global_progress: {
    done: number;
    total: number;
    running: number;
    completed: number;
    failed: number;
  };
  agents: IdentitySummaryRow[];
  matrix: Record<string, Record<string, number>>;
  scored_trials: number;
  scored_trials_by_identity: Record<string, number>;
  metric_counts: Record<string, Record<string, number>>;
  recoverable_trials?: number;
  retried_trials?: number;
  recovered_trials?: number;
  still_failing_trials?: number;
  unfinished_trials?: number;
};

export type ExperimentSummaryResponse = {
  experiment_id: string;
  primary_dimension: "variant-first" | "benchmark-first";
  run_count: number;
  global_progress: {
    done: number;
    total: number;
    running: number;
    completed: number;
    failed: number;
  };
  agents: IdentitySummaryRow[];
  matrix: Record<string, Record<string, number>>;
  runs: Array<{
    run_id: string;
    benchmark: string;
    status: string;
    updated_at_ms: number;
  }>;
};

export type RuntimeEvent = Record<string, unknown> & {
  event_id?: string;
  event?: string;
  ts_ms?: number;
  task_id?: string;
  agent_id?: string;
  variant_id?: string;
  model?: string;
  sample_id?: string;
  trial_key?: string;
  message?: string;
};

export type TrialAttemptRow = {
  attempt_id?: string;
  attempt_no?: number;
  effective?: boolean;
  failure_class?: string | null;
  status?: string;
  started_ts_ms?: number | null;
  ended_ts_ms?: number | null;
  duration_ms?: number | null;
  supersedes_attempt_id?: string | null;
  superseded_by_attempt_id?: string | null;
  retry_source?: string | null;
  scores?: Record<string, unknown>;
};
