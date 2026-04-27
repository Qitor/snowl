# Runtime And Scheduler

This document explains the runtime architecture as implemented today. For future-state ideas, see `docs/runtime_scheduling.md` and `docs/runtime_scheduling_v2.md`. For the seam inventory, see `docs/runtime_known_gaps.md`.

## Key Files

- `snowl/eval.py`
  - Project loading, service construction, queue orchestration, retry queue handling, and run shutdown.
- `snowl/eval_spec.py`, `snowl/planning.py`, `snowl/eval_loop.py`
  - Internal normalized eval spec, plan/trial identity, and one-trial lifecycle side effects.
- `snowl/artifacts.py`, `snowl/observability/events.py`, `snowl/runtime/recovery.py`, `snowl/runtime/policy.py`
  - Internal artifact persistence, live events/runtime state, recovery ledger, and runtime budget policy boundaries.
- `snowl/runtime/engine.py`
  - Trial phases: prepare, execute, score, finalize.
- `snowl/runtime/resource_scheduler.py`
  - Budget objects, semaphores, queue timing stats, provider admission, sandbox-slot wrapping.
- `snowl/runtime/container_runtime.py`
  - Task-declared container contract resolution plus runtime-owned container prepare/finalize wrapper.
- `snowl/runtime/container_providers.py`
  - TerminalBench and OSWorld provider implementations, provider-specific startup mapping, and concrete teardown logic.
- `snowl/runtime/container_contract.py`
  - Normalizes task/sample `runtime_container` metadata into one runtime-owned container request.
- `snowl/runtime/container_lifecycle.py`
  - Runtime-owned registry, lease/release state, run-end cleanup barrier, and preserve-policy handling.
- `snowl/project_config.py`
  - `project.yml` loading, runtime settings, recovery config.
- `snowl/model/openai_compatible.py`
  - OpenAI-compatible client and per-provider admission hook.

## Control Plane vs Execution Plane

Use this split when deciding where a runtime change belongs.

### Control plane

The control plane decides what work exists, how much work may run, and how run state is persisted.

Main control-plane responsibilities:

- project loading and component discovery in `snowl/eval.py`
- plan expansion into `PlanTrial`s
- runtime budget resolution
- queue dispatch, retry queue handling, and in-flight limits
- artifact bootstrap and final artifact writing
- recovery ledger updates
- runtime-state heartbeats and event persistence

If a change affects queue order, resource admission, retry scheduling, artifact status, or run lifecycle, start by reading `snowl/eval.py`.

### Execution plane

The execution plane performs the work of one trial once it has been dispatched.

Main execution-plane responsibilities:

- `prepare_trial_phase()`, `execute_agent_phase()`, `score_trial_phase()`, `finalize_trial_phase()` in `snowl/runtime/engine.py`
- task-declared container resolution plus benchmark-specific environment setup in `snowl/runtime/container_runtime.py` and `snowl/runtime/container_providers.py`
- sandbox and env operations in `snowl/envs/`
- model-call behavior and per-request retries in `snowl/model/openai_compatible.py`

If a change affects task execution semantics, scorer semantics, environment setup, or model-call behavior inside a dispatched trial, start in the execution plane.

## Task-Declared Container Contract And Ownership

Snowl now treats container-backed work as a three-layer contract:

- Task/sample metadata declares whether the trial needs a runtime-managed container and the normalized startup inputs under `runtime_container`.
- Runtime/engine resolves that metadata into a `RuntimeContainerSpec`, creates the provider session, registers the resource, leases it to the trial, and owns release/cleanup.
- Agents consume only the injected `__snowl_container_session`; they must not start or stop containers themselves.

Current implementation details:

- Contract normalization lives in `snowl/runtime/container_contract.py`.
- Runtime registration and cleanup ownership live in `snowl/runtime/container_lifecycle.py`.
- `prepare_trial_phase()` injects both `__snowl_container_session` and `__snowl_runtime_container_spec` into agent context.
- TerminalBench and OSWorld example agents now treat a missing runtime-managed session as a runtime contract violation.

What this does not mean yet:

- runtime-owned containers are not warm-pooled by default
- `spec_hash` does not yet drive dispatch priority or reuse
- `max_container_slots` is still not a universal admission gate across every benchmark container path

## Planner / Eval / Runtime Relationship

### 1. Project and component loading

`snowl eval ...` and `snowl bench run ...` eventually call `run_eval_with_components()` in `snowl/eval.py`.

That function:

- loads or reuses `ProjectConfig`
- normalizes entrypoint facts into internal `EvalSpec`
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
   - delegate one-trial side effects to internal `EvalTrialLifecycle`
   - construct `TrialRequest`
   - call `prepare_trial_phase(request)` under `scheduler.running_trial_slot()`
   - call `execute_agent_phase(prepared)` under the same running-trial admission
   - call `score_trial_phase(prepared, partial)` under `scheduler.scoring_slot()`
   - call `finalize_trial_phase(prepared, outcome)` after scoring
   - record the recovery attempt
   - schedule deferred auto retry if the outcome is retry-eligible
6. In the run `finally` path:
   - cancel outstanding trial tasks best effort
   - run the runtime-owned container cleanup barrier
   - persist cleanup summary before the event writer is closed
7. After all work completes:
   - compute summary and aggregate outputs
   - write final artifacts
   - mark `runtime_state.json` and `manifest.json` completed

### Important nuance

The main eval loop and `execute_trial()` are now aligned on phase order:

- prepare
- execute
- score
- finalize

The remaining mismatch is not phase omission; it is phase admission depth. Prepare still happens while the trial is already holding `running_trial_slot()`, and finalize is still a helper call rather than a separately scheduled phase.

## Known Contract Mismatches

These are confirmed mismatches between exposed runtime surfaces and the main eval-loop behavior.

- `prepare_trial_phase()` is a real helper, but the main eval loop still admits it under `scheduler.running_trial_slot()` semantics. Future scheduler work must not describe prepare as independently admitted today.
- Provider budgets are enforced most strongly at model-call time through `OpenAICompatibleChatClient.set_global_model_call_slot_resolver(...)` and `_acquire_model_slot()`. The dispatch loop does not currently choose the next trial based on provider headroom.
- Runtime-owned container cleanup is centralized for runtime-managed resources, but `max_container_slots` still does not serve as a universal dispatcher gate for every benchmark container prepare path.
- `spec_hash` is computed from the normalized container contract and carried into trial payload/trace, but it does not drive dispatch priority, batching, locality-aware reuse, or warm-pool preference.
- `TaskExecutionPlan` and `TrialDescriptor` exist on `TrialRequest`, but `run_eval_with_components()` does not populate them for repo-level runs. Their presence is not proof of plan-aware scheduling.
- `begin_prepare()` and `begin_finalize()` exist on `ResourceScheduler`, but the main eval loop uses only `running_trial_slot()` and `scoring_slot()` directly.
- Benchmark/sample metadata may still carry raw provider startup fields such as compose paths or OSWorld settings for benchmark compatibility, but runtime ownership decisions must come from the normalized `runtime_container` contract, not from agent-side interpretation of those raw fields.

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

## Runtime-Owned Container Lifecycle

This is the current container ownership model for runtime-managed benchmarks.

### Registration and lease

- `ContainerRuntime.prepare_phase()` resolves one `RuntimeContainerSpec`.
- If `requires_container` is true and a provider exists, runtime acquires the provider session and immediately registers it in `RuntimeContainerLifecycleManager`.
- Registration records at least:
  - `run_id`
  - `trial_id`
  - `benchmark`
  - `provider_name`
  - `spec_hash`
  - concrete identifiers such as `container_id`, `compose_project`, and `compose_file` when available
- The resource is then leased to the current trial.

### Release and default cleanup policy

- `finalize_trial_phase()` releases the runtime-owned container lease.
- Current default policy is conservative:
  - released benchmark containers are marked dirty
  - runtime tears them down immediately
  - warm reuse is not enabled by default
- Explicit preserve behavior is CLI-driven:
  - `--keep-containers`
  - `--keep-failed-containers`

### Run-end cleanup barrier

- `run_eval_with_components()` creates one lifecycle manager per run.
- In the run `finally` path, Snowl calls `cleanup_run(...)` before closing `events.jsonl`.
- The barrier emits:
  - `runtime.cleanup.barrier.start`
  - `runtime.cleanup.barrier.finish`
  - `runtime.cleanup.leak_suspected` when non-preserved survivors remain
- `profiling.json` now includes `container_cleanup`.

### What still stays benchmark-specific

- provider startup/teardown commands still live in:
  - `TerminalBenchProvider`
  - `OSWorldProvider`
- runtime owns *when* they are invoked and how they are tracked
- providers still own *how* the container is actually started and stopped

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

### TerminalBench and OSWorld are the only fully standardized runtime-owned paths today

Snowl has a shared container contract and lifecycle manager now, but the concrete provider adapters are still implemented only for:

- `TerminalBenchProvider`
- `OSWorldProvider`

Future container-backed benchmarks should join this runtime-owned contract instead of adding agent-managed startup code.

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
