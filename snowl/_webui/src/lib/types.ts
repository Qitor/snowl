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
  updated_at_ms: number;
  path: string;
};

export type RunSnapshot = {
  run_id: string;
  experiment_id: string;
  benchmark: string;
  status: "running" | "completed";
  done: number;
  total: number;
  summary: Record<string, unknown>;
  plan: Record<string, unknown>;
  task_monitor: Array<Record<string, unknown>>;
  updated_at_ms: number;
  last_event_id: string | null;
};

export type SummaryResponse = {
  experiment_id: string;
  primary_dimension: "agent-first" | "benchmark-first";
  run_count: number;
  global_progress: {
    done: number;
    total: number;
    running: number;
    completed: number;
    failed: number;
  };
  agents: Array<{
    agent_id: string;
    metrics: Record<string, number>;
    rank_score: number;
  }>;
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
  sample_id?: string;
  trial_key?: string;
  message?: string;
};
