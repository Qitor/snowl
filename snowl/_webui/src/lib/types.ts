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
  status: "running" | "completed";
  done: number;
  total: number;
  failed: number;
  updated_at_ms: number;
  path: string;
  variant_count: number;
  models: string[];
  is_live: boolean;
};

export type RunSnapshot = {
  run_id: string;
  experiment_id: string;
  benchmark: string;
  status: "running" | "completed";
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
};

export type RunSummaryResponse = {
  run_id: string;
  experiment_id: string;
  benchmark: string;
  status: "running" | "completed";
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
