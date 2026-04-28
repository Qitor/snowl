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
- Built-in benchmark adapters for `strongreject`, `terminalbench`, `osworld`, `toolemu`, `agentsafetybench`, `xstest`, `coconot`, `fortress_adversarial`, `fortress_benign`, `agentharm`, `agentharm_benign`, `agent_bench_os`, `agentdojo`, `bfcl`, `ipi_coding_agent`, `cybermetric_80`, `cybermetric_500`, `cybermetric_2000`, `cybermetric_10000`, `sec_qa_v1`, `sec_qa_v2`, `sevenllm_mcq_en`, `sevenllm_mcq_zh`, plus generic `jsonl` and `csv`.
- Third-party/local benchmark adapters can be loaded with `--adapter module.py:object`; `snowl bench scaffold` creates a JSONL-oriented adapter template.
- `snowl suite check` and `snowl suite run` execute a simple sequential multi-benchmark suite and write `.snowl/suites/<suite_run_id>/suite_summary.json`.
- Built-in baseline agents in `snowl/agents/chat_agent.py` and `snowl/agents/react_agent.py`.
- Remote benchmark asset helpers can load pinned Hugging Face datasets, Hugging Face snapshot files, and checksum-verified direct URLs into `.snowl/cache/benchmarks` or `SNOWL_BENCHMARK_CACHE`. These remote dataset paths require the optional `safety_assets` dependencies.
- Run artifacts under `.snowl/runs/<run_id>/`.
- Plain CLI eval flow plus an auto-started web monitor sidecar.
- Recovery via `snowl retry <run_id>` and deferred in-run auto-retry for non-success trials.
- Internal eval control-plane helpers for normalized specs, planning, runtime policy, artifact writing, event persistence, trial lifecycle, and recovery. These helpers are not public extension APIs yet.

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
- TerminalBench and OSWorld now use a task-declared `runtime_container` contract that runtime resolves before agent execution.
- Runtime-owned benchmark container resources are registered, leased, released, and summarized by a shared lifecycle manager.
- `runtime_container` now supports provider-name-first v2 fields for workspace, init/start/check commands, network, env, mounts, artifacts, and resource limits while retaining legacy startup fields.
- Runtime-owned per-trial workspaces can materialize source files, inject `workspace_dir`, snapshot before/after files, and expose workspace diff metadata to scorers.
- Samples can restrict available tools with `metadata.tool_names` or `metadata.target_functions`; missing requested tools fail in prepare with a non-retryable validation error.
- Samples can also declare dynamic OpenAI-style tool schemas in `metadata.tool_schemas`; runtime converts them into `ToolSpec`s, merges them with project tools, and fails prepare on schema conflicts.
- Agent-oriented scorer primitives now cover normalized trace extraction, answer matching, function-call matching, trace policy, command checks, workspace diffs, canary leakage, state transitions, checkpoint aggregation, rubric judges, and grouped metrics.
- `compose_terminal` and `docker_container` are available as generic runtime container providers and can be selected through `runtime_container.provider_name`.
- The `toolemu` built-in scorer is Snowl-native and no longer imports or executes an external evaluator runtime.
- Repo-level `run_eval()` now performs trial finalize and a run-end cleanup barrier before closing live event output.
- Deferred auto-retry and manual `snowl retry` both reuse a recovery ledger instead of inventing a separate retry system.
- Live observability artifacts are written early enough for the monitor to show running runs before completion.
- `run_eval_with_components()` still owns queue orchestration, while one-trial prepare/execute/score/finalize side effects are routed through an internal `EvalTrialLifecycle` helper.

## Runtime / Scheduler Status By Topic

| Topic | Implemented now | Partially implemented / inconsistent | Planned / not yet real |
| --- | --- | --- | --- |
| Provider budgets | `provider_budgets` are real controls and model calls acquire `scheduler.provider_slot(...)` through `OpenAICompatibleChatClient`. | Dispatch does not prioritize by provider headroom, so trials can be admitted and then wait later on model-call slots. | Scheduler-visible provider-aware dispatch and richer provider backpressure policies. |
| Prepare phase | `prepare_trial_phase()` resolves workspaces, task-declared container contracts, and sandbox setup under `begin_prepare()`. | The outer dispatch loop is still coroutine-based rather than a fully materialized prepare worker pool. | Queue-level prepare batching and locality-aware reuse. |
| Score decoupling | Score is admitted separately under `begin_score()` and no longer uses the same slot as execution. | The outer dispatch loop still bounds total in-flight coroutines coarsely. | Richer score queue prioritization. |
| Finalize behavior | `finalize_trial_phase()` is admitted through `begin_finalize()` and releases runtime-owned containers. | Finalize has phase stats but not a dedicated concurrency limit. | Dedicated finalize policies if teardown becomes a bottleneck. |
| Runtime-owned container lifecycle | TerminalBench, OSWorld, compose_terminal, and docker_container sessions are registered with run/trial ownership, released at trial end, and covered by a run-end cleanup barrier. | Warm reuse is intentionally absent by default. | Warm-pool reuse and broader provider-specific diagnostics. |
| Container slot enforcement | `max_container_slots` gates runtime-managed container prepare through `begin_prepare()` and sandbox runtimes through the scheduled sandbox wrapper. | Local non-container workspace prepare is not gated by container slots. | More detailed prepare resource classes. |
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

- `TaskExecutionPlan` and `TrialDescriptor` are populated for repo-level trial lifecycle admission, but not yet used for smarter dispatch ordering.
- The eval trial lifecycle uses scheduler prepare/execute/score/finalize APIs; the outer loop still handles dispatch and retry queues.
- `TrialRequest.execution_plan` and `TrialRequest.trial_descriptor` are populated by `EvalTrialLifecycle`.
- `spec_hash` is computed from normalized container contracts, but the runtime does not yet use it for locality-aware dispatch, warm-pool reuse, or batching.
- `max_container_slots` gates runtime-managed container-provider prepare paths selected by `runtime_container.requires_container`.
- The main dispatch loop is still close to FIFO: it drains `fresh_queue` in plan order, then consumes deferred retries when ready.
- Provider capacity is enforced at model-call admission time, not by a scheduler that prioritizes work based on provider headroom.
- Task/sample rows may still carry raw benchmark startup fields such as compose paths or OSWorld settings, but runtime ownership decisions should come from the normalized `runtime_container` contract.
- `EvalSpec`, `PlanBuilder`, `RuntimePolicy`, `RunArtifactStore`, `RunEventBus`, `EvalTrialLifecycle`, and `RecoveryManager` are internal boundaries. They stabilize code organization but do not yet define plugin or YAML v2 contracts.

## Known Bottlenecks

- Container-heavy benchmarks still pay prepare/build/setup cost close to trial execution rather than through a richer prepare pipeline.
- TerminalBench and OSWorld now clean up more reliably, but they can still feel more like gated whole-trial concurrency than fully pipelined phase scheduling.
- Warm reuse is intentionally absent for benchmark containers by default: runtime destroys them on release unless preserve flags are explicitly enabled.
- Build concurrency and container concurrency are only partially separated in practice.
- Cross-run scheduling and caching do not exist; runs are isolated local executions.

## Known Technical Debt

These are current debt items, not intentional abstractions to depend on:

- `docs/runtime_scheduling.md` and `docs/runtime_scheduling_v2.md` describe desired direction more than current behavior.
- Runtime-owned container lifecycle is standardized for TerminalBench and OSWorld, but other future container-backed benchmarks still need to adopt the same task-declared contract instead of inventing new startup side effects.
- `max_container_slots` still does not uniformly govern every container prepare path, even though runtime now owns cleanup for the standardized ones.
- `max_running_trials` defaults to `1` for docker-like tasks unless explicitly overridden, which is safe but still blunt.
- The web UI has two trees (`webui/` and `snowl/_webui/`) that can drift if changes are not mirrored intentionally.

## Deliberate MVP Tradeoffs

These look limited because they are deliberate scope choices for now:

- Single-machine operation only.
- One provider block per project.
- One scorer per trial.
- Generic benchmark adapters (`jsonl`, `csv`) stay simple and local instead of introducing plugin infrastructure first.
- External benchmark adapters are local-file based only; there is no package marketplace, dependency installer, or remote plugin trust model yet.
- Suite execution is sequential. There is no cross-benchmark scheduler or shared admission policy beyond the runtime settings passed into each child benchmark run.
- Auto web monitor startup is operator-focused and local; it is not a remote service.

## Planned But Not Implemented

The following show up in docs and scaffolding, but are not current runtime behavior yet:

- Scheduler-driven phase planning with explicit `TrialDescriptor` / `TaskExecutionPlan` inputs.
- Locality-aware dispatch using `spec_hash`.
- Dedicated queue workers for prepare/finalize beyond the current per-trial phase admission.
- Benchmark container warm reuse or pooling by default.
- More sophisticated blocked-group/canary-first scheduling.
- Distributed or multi-machine execution.

## Current Mismatches To Watch

- Treat `docs/runtime_scheduling*.md` as design notes, not source-of-truth behavior docs.
- Treat `run_eval()` as the runtime path that matters for end-to-end repo behavior.
- Do not assume task/sample raw benchmark fields are the ownership contract; runtime now resolves `runtime_container` and agents must not use raw compose/OSWorld fields to decide whether to start containers.
- Do not assume `max_container_slots` applies to non-container local workspace materialization.
- Do not assume `TaskExecutionPlan`, `TrialDescriptor`, or `spec_hash` drive dispatch order yet.
- Do not assume multiple providers, distributed execution, or cross-run pooling exist just because the scheduler types look extensible.
