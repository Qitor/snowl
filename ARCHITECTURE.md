# Snowl Architecture

This document describes the current architecture of `snowl` and the direction required to turn it into an industrial-grade evaluation platform.

## 1. System Boundary

Snowl is currently a local, single-machine evaluation platform with four user-facing surfaces:

1. authoring surface
   - `project.yml`
   - `task.py`
   - `agent.py`
   - `scorer.py`
   - `tool.py`
2. execution surface
   - `snowl eval path/to/project.yml`
   - `snowl bench run <benchmark> --project path/to/project.yml`
3. artifact surface
   - `.snowl/runs/<run_id>/...`
4. observability surface
   - plain CLI operator logs
   - Next.js Web monitor

It is not yet a distributed scheduler.

## 2. Primary Execution Model

The real execution unit is:

- `Task x AgentVariant x Sample`

Important nuance:

- `Task` defines the workload and environment expectations
- `AgentVariant` binds one executable identity to one model/configuration
- `Sample` is the concrete row executed by the trial
- one active `Scorer` evaluates each trial today

## 3. Main Subsystems

### 3.1 Project configuration and discovery

Main code:

- `snowl/project_config.py`
- `snowl/eval.py`
- `snowl/agents/model_variants.py`
- `snowl/core/`

Responsibilities:

- load `project.yml`
- resolve project root and eval code paths
- resolve provider config
- expand `agent_matrix.models` into `AgentVariant`s
- keep `judge.model` separate from tested models
- validate `Task`, `Agent`, `Scorer`, and `ToolSpec`

Current product rule:

- `project.yml` is the formal source of truth
- `eval.code.base_dir` and module paths explicitly describe where the eval code lives
- user-facing provider and benchmark config should not depend on env vars

### 3.2 Planning and run bootstrap

Main code:

- `snowl/eval.py`

Responsibilities:

- filter tasks / agents / variants
- expand the execution plan
- compute `run_id` and default `experiment_id`
- create live artifact directories
- write early bootstrap artifacts
- emit bootstrap information to CLI and Web observers

Important current behavior:

- `manifest.json`, `plan.json`, and live `profiling.json` skeletons are written at run startup
- `events.jsonl` is live-appended during execution
- CLI owns the lifecycle of its auto-started Web monitor sidecar

### 3.3 Trial execution engine

Main code:

- `snowl/runtime/engine.py`

Responsibilities:

- construct `TrialRequest`
- prepare initial `AgentState`
- inject `task_id`, `sample_id`, `variant_id`, and `model`
- emit runtime events
- execute agent logic
- execute scorer logic
- normalize output into `TaskResult`

The engine now exposes two runtime phases explicitly:

- `execute_agent_phase(...) -> PartialTrialResult`
- `score_trial_phase(...) -> FinalTrialOutcome`

This decoupling allows scoring to stop occupying the same slot as agent execution.

### 3.4 Resource scheduler

Main code:

- `snowl/runtime/resource_scheduler.py`
- `snowl/eval.py`

Current scheduler model is provider-aware and phase-aware.

It separately controls:

- `max_running_trials`
- `max_container_slots`
- `max_builds`
- `max_scoring_tasks`
- `provider_budgets[provider_id]`

Key semantics:

- agent execution uses `running_trial_slot()`
- scoring uses `scoring_slot()`
- remote model calls use `provider_slot(provider_id)`
- build/setup work uses `build_slot()`
- sandbox/container capacity uses container/sandbox slots

This is the current local control plane for concurrency.

### 3.5 Container lifecycle orchestration

Main code:

- `snowl/runtime/container_runtime.py`
- `snowl/runtime/container_providers.py`
- benchmark-specific launchers under `snowl/benchmarks/*`

Responsibilities:

- resolve the correct container provider for a benchmark
- translate trial context into benchmark-specific lifecycle steps
- isolate resources by `task_id + sample_id + variant_id`
- emit pretask and environment lifecycle events

Current rule:

- container trial resources must be variant-aware
- `variant_id` is part of compose project names, log paths, and related resource names

This is what makes multi-model TerminalBench and OSWorld runs safe.

### 3.6 Aggregation and artifacts

Main code:

- `snowl/eval.py`
- `snowl/aggregator/`

Durable run artifacts include at least:

- `manifest.json`
- `plan.json`
- `summary.json`
- `aggregate.json`
- `profiling.json`
- `trials.jsonl`
- `events.jsonl`
- `metrics_wide.csv`
- `run.log`

This run directory is the contract boundary between execution and observability.

### 3.7 Observability

#### CLI

Main code:

- `snowl/cli.py`
- `snowl/ui/console.py`

Current behavior:

- default mode is plain foreground operator logging
- `--cli-ui` enables the legacy live console UI
- the auto-started Web monitor runs as a managed background sidecar

#### Web monitor

Main code:

- `webui/`
- `snowl/_webui/`
- `snowl/web/runtime.py`
- `webui/src/server/monitor.ts`

Current behavior:

- Next.js full-stack monitor
- `/` is the run gallery / operator board
- `/runs/[runId]` is the single-run workspace
- `/compare` is a secondary history view
- monitor indexes runs from `.snowl/runs/`
- monitor consumes live `events.jsonl` and run artifacts

Repo fact:

- `webui/` is the editable source of truth
- `snowl/_webui/` is the packaged mirror

## 4. Data Flow

At a high level:

```text
project.yml
  -> project config + code path resolution
  -> agent matrix expansion
  -> eval plan
  -> resource scheduler
  -> execute phase / score phase
  -> artifacts + live events
  -> CLI + Web monitor
```

Concrete flow:

1. `snowl eval path/to/project.yml` loads the project config
2. Snowl loads `task.py`, `agent.py`, `scorer.py`, and optional `tool.py` from `eval.code`
3. model entries expand into `AgentVariant`s
4. `PlanTrial`s are built and scheduled
5. execute and score phases consume different budgets
6. artifacts and events are written continuously
7. CLI and Web consume the same underlying run facts

## 5. Why Provider-Aware Scheduling Matters

In practice, remote provider limits are usually the real bottleneck for agent evaluation.

That is why Snowl now treats provider concurrency as a first-class resource:

- agent remote requests consume provider budget
- judge remote requests consume provider budget
- if agent and judge share one provider, they share the same budget

This is more correct than thinking only in terms of global worker count.

## 6. Current Strengths

The platform already has several strong foundations:

- strict execution contract across QA, terminal, and GUI tasks
- YAML-first project authoring
- multi-model expansion through `AgentVariant`
- variant-aware container isolation
- live structured event stream
- usable run-first operator workflows

These are the foundations to preserve while scaling the runtime.

## 7. Current Gaps

Snowl still needs more work before it feels fully industrial:

- better phase scheduling heuristics and queueing policy
- stronger warm-pool / spec-hash reuse
- richer backpressure and stall diagnosis
- more benchmark-internal config routed through YAML instead of legacy env fallbacks
- stronger quantitative benchmarking for container-heavy workloads
- more robust resume/retry semantics across phases

## 8. Near-Term Direction

The current near-term architecture priorities are:

1. finish the YAML-first config migration across all official workflows
2. harden provider-aware, phase-aware scheduling
3. quantify runtime throughput improvements with reproducible baselines
4. improve container-heavy benchmark reliability and diagnostics
5. keep CLI, Web, and artifact contracts aligned
