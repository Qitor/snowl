# Runtime And Scheduler

This document explains the runtime architecture as implemented today. For future-state ideas, see `docs/runtime_scheduling.md` and `docs/runtime_scheduling_v2.md`.

## Key Files

- `snowl/eval.py`
  - Project loading, plan expansion, runtime budget resolution, main dispatch loop, recovery, artifact writing.
- `snowl/runtime/engine.py`
  - Trial phases: prepare, execute, score, finalize.
- `snowl/runtime/resource_scheduler.py`
  - Budget objects, semaphores, queue timing stats, provider admission, sandbox-slot wrapping.
- `snowl/runtime/container_runtime.py`
  - Benchmark-aware container prepare/finalize wrapper.
- `snowl/runtime/container_providers.py`
  - TerminalBench and OSWorld provider implementations and `spec_hash` calculation.
- `snowl/project_config.py`
  - `project.yml` loading, runtime settings, recovery config.
- `snowl/model/openai_compatible.py`
  - OpenAI-compatible client and per-provider admission hook.

## Planner / Eval / Runtime Relationship

### 1. Project and component loading

`snowl eval ...` and `snowl bench run ...` eventually call `run_eval_with_components()` in `snowl/eval.py`.

That function:

- loads or reuses `ProjectConfig`
- loads `task.py`, `agent.py`, `scorer.py`, optional `tool.py`
- expands agents into `AgentVariant`s when author code uses `build_model_variants(...)`
- builds an `EvalPlan` made of `PlanTrial`s

### 2. Runtime budget resolution

Before any trials run, `run_eval_with_components()` resolves runtime controls using:

- CLI overrides
- `project.yml` runtime values
- repo defaults and heuristics

Important current rules:

- Default `max_running_trials` is roughly CPU-based when unset.
- Default `max_builds` is `2`.
- Default `max_scoring_tasks` is `max_running_trials`.
- `max_container_slots` uses `_auto_container_slots(...)` when left as `auto`.
- Docker-like tasks force `max_running_trials=1` unless the user explicitly set a value.

### 3. Scheduler and provider hookup

`run_eval_with_components()` creates `ResourceScheduler(...)` and then wires:

- `set_compose_build_slot_factory(scheduler.build_slot)`
- `OpenAICompatibleChatClient.set_global_model_call_slot_resolver(...)`

That second hook is the current provider-budget enforcement point.

## Trial Execution Flow

The main eval loop in `snowl/eval.py` is the real runtime behavior for repo-level runs.

### Actual flow today

1. Write early live artifacts and start runtime-state heartbeats.
2. Build `fresh_queue` from plan order.
3. Maintain a separate `recovery_queue` for deferred auto retries.
4. Dispatch up to `max_running_trials + max_scoring_tasks` in-flight trial coroutines.
5. For each trial:
   - construct `TrialRequest`
   - call `execute_agent_phase(request)` under `scheduler.running_trial_slot()`
   - call `score_trial_phase(request, partial)` under `scheduler.scoring_slot()`
   - record the recovery attempt
   - schedule deferred auto retry if the outcome is retry-eligible
6. After all work completes:
   - compute summary and aggregate outputs
   - write final artifacts
   - mark `runtime_state.json` and `manifest.json` completed

### Important nuance

`execute_agent_phase(request)` internally performs prepare work when given a raw `TrialRequest`, because it first calls `prepare_trial_phase(request)`.

So in the main eval loop:

- prepare currently happens inside the coroutine admitted by `running_trial_slot()`
- score happens separately under `scoring_slot()`
- finalize is not invoked from the main eval loop today

By contrast, `execute_trial()` in `snowl/runtime/engine.py` does:

- prepare
- execute
- score
- finalize

That mismatch is real and should be treated as current technical debt.

## Resource Budgets

### `max_running_trials`

- Enforced directly in the eval loop through `scheduler.running_trial_slot()`.
- Currently covers the coroutine that includes both prepare and execute work when the request is not pre-prepared.

### `max_scoring_tasks`

- Enforced directly in the eval loop through `scheduler.scoring_slot()`.
- Lets scoring overlap with other trial execution instead of blocking the main running-trial quota.

### `provider_budgets`

- Enforced by `OpenAICompatibleChatClient` through the scheduler slot resolver.
- Applies to any model call that uses `OpenAICompatibleConfig.provider_id`.
- Agent calls and judge/model-as-judge calls share the same budget when they use the same provider id.

### `max_builds`

- Exposed by `scheduler.build_slot()`.
- Used by compose-build paths through `set_compose_build_slot_factory(...)`.
- This is real, but it is narrower than a full prepare scheduler.

### `max_container_slots`

- Exposed in the scheduler and tracked in profiling stats.
- Used to wrap sandbox runtimes via `scheduler.wrap_sandbox_runtime(...)`.
- Not yet a universal gate on all container-provider prepare paths in the main eval loop.

## Current Provider Budget Behavior

Budget resolution in `snowl/eval.py` currently does the following:

- If `project.yml` defines a provider id and no budget was supplied for it, Snowl inserts one equal to `max(max_running_trials, max_scoring_tasks)`.
- If there is no project provider and no explicit provider budgets, Snowl inserts `default`.
- The model client acquires provider slots per request, not per trial.

Practical consequence:

- A queued trial can start running, then block later on provider admission.
- Provider headroom is visible to the scheduler, but not yet used to prioritize which trial should start next.

## Current Execute / Score Decoupling

This part is already implemented and useful:

- execution and scoring use different quotas
- scoring no longer consumes the same admission slot as agent execution
- profiler output distinguishes queue wait and active counts for these phases

What is not implemented yet:

- independent prepare scheduling
- independent finalize scheduling in the main eval loop
- phase-level retry
- scheduler decisions based on predicted plan cost

## Container And Runtime Limitations

### Container prepare still lives close to execution

`prepare_trial_phase()` creates `ContainerRuntime` and calls `container_runtime.prepare_phase()` before agent execution. This keeps the code organized, but it is not yet a fully separate scheduler-managed prepare pipeline.

### `spec_hash` is not yet used for scheduling

Container providers compute `spec_hash`, but the dispatcher does not yet:

- batch matching trials
- prefer warm-locality
- reuse prepare work across compatible trials

### TerminalBench and OSWorld are benchmark-specific

Container handling is still concentrated in:

- `TerminalBenchProvider`
- `OSWorldProvider`

Snowl does not yet have a generalized container orchestration layer that every benchmark shares equally.

### Sandboxes and containers are not the same path

- Sandbox-backed tasks can use `scheduler.wrap_sandbox_runtime(...)`.
- Benchmark container providers also run benchmark-specific prepare logic.

That split is one reason `max_container_slots` is not yet a universal control plane.

## Retry Behavior

Snowl currently has three layers of retry/recovery behavior:

### Provider HTTP retry

`snowl/model/openai_compatible.py` retries retryable HTTP and timeout failures with exponential backoff up to `config.max_retries`.

### In-run deferred auto retry

Configured in `project.yml` under `runtime.recovery`.

Current behavior:

- only `retry_timing: deferred` is accepted
- non-success attempts can be enqueued into `recovery_queue`
- retries happen after `backoff_ms`
- `max_auto_retries_per_trial` caps in-run auto retries

### Manual run retry

`snowl retry <run_id>`:

- checks `runtime_state.json` to ensure the run is not still active
- reuses the existing run directory and run id
- reloads only unfinished or non-success effective trials

## Where Scheduling Is Still Shallow Or FIFO-Like

The runtime is still close to FIFO in several ways:

- `fresh_queue` is drained in plan order with `pop(0)`.
- `recovery_queue` dispatches the first ready retry item.
- `max_inflight_trials` is derived from quotas, but there is no fairness or locality policy beyond queue order.
- `TaskExecutionPlan.priority` and `TrialDescriptor.phase` are not yet driving dispatch.

Use this mental model:

Snowl already has multi-budget throttling and a coarse execute/score split, but not a mature phase-aware dispatcher yet.
