# Current State

This file describes the implementation that exists today. It is intentionally separate from planning docs such as `docs/runtime_scheduling.md` and `docs/runtime_scheduling_v2.md`, which are forward-looking. For the runtime seam inventory, see `docs/runtime_known_gaps.md`.

## Implemented Now

### Product Shape

Snowl currently supports:

- Local single-machine evaluation.
- YAML-first project entrypoints through `project.yml`.
- One provider block per project, with only `provider.kind: openai_compatible` supported in `snowl/project_config.py`.
- Multi-model sweeps through `agent_matrix.models`, expanded into `AgentVariant`s.
- One active scorer per trial.
- Built-in benchmark adapters for `strongreject`, `terminalbench`, `osworld`, `toolemu`, `agentsafetybench`, plus generic `jsonl` and `csv`.
- Built-in baseline agents in `snowl/agents/chat_agent.py` and `snowl/agents/react_agent.py`.
- Run artifacts under `.snowl/runs/<run_id>/`.
- Plain CLI eval flow plus an auto-started web monitor sidecar.
- Recovery via `snowl retry <run_id>` and deferred in-run auto-retry for non-success trials.

### Runtime and Scheduler

The runtime already has meaningful budget controls:

- `max_running_trials`
- `max_container_slots`
- `max_builds`
- `max_scoring_tasks`
- `provider_budgets`

What works well today:

- Local QA-style tasks benefit from `max_running_trials`.
- Scoring is decoupled from agent execution at a coarse level: the main eval loop executes under `running_trial_slot()` and scores under `scoring_slot()`.
- Provider budgets are enforced for OpenAI-compatible model calls through `OpenAICompatibleChatClient` and `scheduler.provider_slot(...)`.
- Deferred auto-retry and manual `snowl retry` both reuse a recovery ledger instead of inventing a separate retry system.
- Live observability artifacts are written early enough for the monitor to show running runs before completion.

## Runtime / Scheduler Status By Topic

| Topic | Implemented now | Partially implemented / inconsistent | Planned / not yet real |
| --- | --- | --- | --- |
| Provider budgets | `provider_budgets` are real controls and model calls acquire `scheduler.provider_slot(...)` through `OpenAICompatibleChatClient`. | Dispatch does not prioritize by provider headroom, so trials can be admitted and then wait later on model-call slots. | Scheduler-visible provider-aware dispatch and richer provider backpressure policies. |
| Prepare phase | `prepare_trial_phase()` exists and performs container/sandbox setup. | In main eval flow, prepare still runs under `running_trial_slot()` semantics via `execute_agent_phase(request)`. | Independently admitted prepare scheduling. |
| Score decoupling | Score is admitted separately under `scoring_slot()` and no longer uses the same slot as execution. | The split is coarse; prepare and finalize are not independently scheduled in the main loop. | Fully phase-aware scheduling across prepare, execute, score, and finalize. |
| Finalize behavior | `finalize_trial_phase()` exists and is used by `execute_trial()`. | The main eval loop does not consistently invoke it, so repo-level runs and standalone engine runs are not identical. | Finalize as a normal, explicitly scheduled phase in repo-level evals. |
| Container slot enforcement | `max_container_slots` exists and is tracked in scheduler/profiling data. Sandbox runtimes can be wrapped with it. | It is not a universal admission gate across every benchmark container prepare path in the main eval loop. | One control plane that gates container-backed work consistently. |
| `spec_hash` locality | Container providers compute `spec_hash` and trial payloads/traces can carry it. | Queue dispatch does not use it for batching, warm-locality, or reuse preference. | Locality-aware dispatch and stronger prepare reuse. |
| Phase-aware retry | Provider HTTP retry and deferred whole-trial auto retry are real. | Retry is still mostly whole-trial; prepare/score/finalize are not retried as distinct scheduled phases. | Phase-specific retry and recovery policies. |

### Observability

Current live run artifacts include:

- `manifest.json`
- `plan.json`
- `profiling.json`
- `runtime_state.json`
- `events.jsonl`
- Later-completion artifacts such as `summary.json`, `aggregate.json`, `outcomes.json`, `metrics_wide.csv`

The web monitor currently indexes runs from `.snowl/runs/` and uses:

- `manifest.json` and `plan.json` for static run metadata
- `events.jsonl` for live event ingestion
- `runtime_state.json` to distinguish active, cancelled, and stale runs
- `summary.json` and `aggregate.json` for completed-run summaries

## Partially Implemented or Transitional

These areas are real, but still coarse or inconsistent:

- `TaskExecutionPlan` and `TrialDescriptor` exist in `snowl/runtime/resource_scheduler.py`, but `run_eval_with_components()` does not yet populate or use them for smarter dispatch.
- The scheduler exposes prepare/execute/score/finalize APIs, but the main eval loop only uses execute and score admission directly.
- `TrialRequest.execution_plan` and `TrialRequest.trial_descriptor` exist, but repo-level eval code does not populate them.
- `spec_hash` is computed by container providers, but the runtime does not yet use it for locality-aware dispatch, warm-pool reuse, or batching.
- `max_container_slots` is wired into sandbox wrapping and scheduler APIs, but not all container-provider prepare paths are centrally admitted through that budget yet.
- The main dispatch loop is still close to FIFO: it drains `fresh_queue` in plan order, then consumes deferred retries when ready.
- Provider capacity is enforced at model-call admission time, not by a scheduler that prioritizes work based on provider headroom.

## Known Bottlenecks

- Container-heavy benchmarks still pay prepare/build/setup cost close to trial execution rather than through a richer prepare pipeline.
- TerminalBench and OSWorld can still feel more like gated whole-trial concurrency than fully pipelined phase scheduling.
- Warm reuse is limited: the runtime has sandbox wrapping but no locality-aware queueing by `spec_hash`.
- Build concurrency and container concurrency are only partially separated in practice.
- Cross-run scheduling and caching do not exist; runs are isolated local executions.

## Known Technical Debt

These are current debt items, not intentional abstractions to depend on:

- `docs/runtime_scheduling.md` and `docs/runtime_scheduling_v2.md` describe desired direction more than current behavior.
- The main `run_eval()` path currently calls `execute_agent_phase()` and `score_trial_phase()` directly, while `execute_trial()` goes through prepare, execute, score, and finalize. That means standalone engine behavior and eval-loop behavior are not perfectly aligned.
- `max_running_trials` defaults to `1` for docker-like tasks unless explicitly overridden, which is safe but still blunt.
- The web UI has two trees (`webui/` and `snowl/_webui/`) that can drift if changes are not mirrored intentionally.

## Deliberate MVP Tradeoffs

These look limited because they are deliberate scope choices for now:

- Single-machine operation only.
- One provider block per project.
- One scorer per trial.
- Generic benchmark adapters (`jsonl`, `csv`) stay simple and local instead of introducing plugin infrastructure first.
- Auto web monitor startup is operator-focused and local; it is not a remote service.

## Planned But Not Implemented

The following show up in docs and scaffolding, but are not current runtime behavior yet:

- Scheduler-driven phase planning with explicit `TrialDescriptor` / `TaskExecutionPlan` inputs.
- Locality-aware dispatch using `spec_hash`.
- Broad prepare/finalize admission through `begin_prepare()` and `begin_finalize()`.
- More sophisticated blocked-group/canary-first scheduling.
- Distributed or multi-machine execution.

## Current Mismatches To Watch

- Treat `docs/runtime_scheduling*.md` as design notes, not source-of-truth behavior docs.
- Treat `run_eval()` as the runtime path that matters for end-to-end repo behavior, even when `execute_trial()` looks slightly cleaner in isolation.
- Do not assume `prepare_trial_phase()` or `finalize_trial_phase()` are independently scheduled just because helpers exist.
- Do not assume `max_container_slots` fully governs every container-backed path yet.
- Do not assume `TaskExecutionPlan`, `TrialDescriptor`, or `spec_hash` are wired into dispatch just because the types exist.
- Do not assume multiple providers, distributed execution, or cross-run pooling exist just because the scheduler types look extensible.
