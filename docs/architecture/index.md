# Architecture

Snowl's runtime architecture, control plane, and execution plane.

---

## Overview

Snowl follows a **control plane / execution plane** split. The control plane
decides what work exists and how much may run concurrently. The execution plane
performs the work of individual trials.

```
project.yml
    │
    ▼
Control Plane (snowl/eval.py)
    │  • Project loading & component discovery
    │  • Plan expansion into PlanTrials
    │  • Runtime budget resolution
    │  • Queue dispatch & retry handling
    │  • Artifact persistence
    │
    ▼
Execution Plane (snowl/runtime/engine.py)
    │  • prepare_trial_phase()
    │  • execute_agent_phase()
    │  • score_trial_phase()
    │  • finalize_trial_phase()
    │
    ▼
Run Artifacts (.snowl/runs/<run_id>/)
```

---

## Core contract

The extension surface is intentionally small:

```
Task ──── defines samples and environment needs
Agent ──── the system under test
Scorer ─── evaluates agent output
ToolMiddleware ──── intercepts tool calls and results
```

Everything else is internal infrastructure.

---

## Key modules

### Control plane

| Module | Responsibility |
|--------|---------------|
| `snowl/eval.py` | Project loading, queue orchestration, retry, shutdown |
| `snowl/eval_spec.py` | Internal normalized eval spec |
| `snowl/planning.py` | Plan/trial identity |
| `snowl/eval_loop.py` | One-trial lifecycle side effects |
| `snowl/artifacts.py` | Artifact persistence |
| `snowl/observability/events.py` | Live events |
| `snowl/runtime/recovery.py` | Recovery ledger |
| `snowl/runtime/policy.py` | Runtime budget policy |
| `snowl/project_config.py` | project.yml loading and validation |

### Execution plane

| Module | Responsibility |
|--------|---------------|
| `snowl/runtime/engine.py` | Trial phases: prepare, execute, score, finalize |
| `snowl/runtime/resource_scheduler.py` | Budgets, semaphores, provider admission |
| `snowl/runtime/container_runtime.py` | Container prepare/finalize wrapper |
| `snowl/runtime/container_providers.py` | TerminalBench and OSWorld providers |
| `snowl/runtime/container_lifecycle.py` | Container registry, lease/release, cleanup |
| `snowl/envs/` | Local, terminal, GUI, sandbox abstractions |

### Benchmark adapters

| Module | Responsibility |
|--------|---------------|
| `snowl/bench.py` | `snowl bench` orchestration |
| `snowl/benchmarks/registry.py` | Adapter registration |
| `snowl/benchmarks/external.py` | Third-party adapter loading and scaffolding |
| `snowl/benchmarks/<name>/adapter.py` | Per-benchmark adapter |
| `snowl/benchmarks/<name>/scorer.py` | Per-benchmark scoring |

### Agents and models

| Module | Responsibility |
|--------|---------------|
| `snowl/agents/react_agent.py` | Built-in ReAct agent |
| `snowl/agents/chat_agent.py` | Built-in single-call agent |
| `snowl/agents/model_variants.py` | Multi-model variant expansion |
| `snowl/model/openai_compatible.py` | OpenAI-compatible client with provider admission |

---

## Trial execution flow

1. Write early live artifacts and start runtime-state heartbeats
2. Build `fresh_queue` from plan order
3. Maintain a `recovery_queue` for deferred auto retries
4. Dispatch up to `max_running_trials + max_scoring_tasks` concurrent trial coroutines
5. For each trial:
   - Delegate to `EvalTrialLifecycle`
   - `prepare_trial_phase(request)` — resolve environments, containers, tools
   - `execute_agent_phase(prepared)` — run the agent
   - `score_trial_phase(prepared, partial)` — run the scorer
   - `finalize_trial_phase(prepared, outcome)` — release resources, write artifacts
6. In the `finally` path: cancel outstanding tasks, run container cleanup barrier
7. After completion: compute aggregates, write final artifacts

---

## Resource budgets

| Budget | Enforcement | Scope |
|--------|-------------|-------|
| `max_running_trials` | `scheduler.running_trial_slot()` | Concurrent trial executions |
| `max_scoring_tasks` | `scheduler.scoring_slot()` | Concurrent scoring tasks |
| `provider_budgets` | `OpenAICompatibleChatClient` per-request | Concurrent model API calls |
| `max_builds` | `scheduler.build_slot()` | Concurrent container builds |
| `max_container_slots` | Wraps sandbox runtimes | Concurrent container/sandbox slots |

### Provider budget behavior

- If `project.yml` defines a provider and no budget was supplied, Snowl inserts
  one equal to `max(max_running_trials, max_scoring_tasks)`
- The model client acquires provider slots per request, not per trial
- Agent calls and judge calls share the same budget when using the same provider

---

## Container lifecycle

For runtime-managed benchmarks (TerminalBench, OSWorld):

1. Task/sample metadata declares `runtime_container` needs
2. Runtime resolves the metadata into `RuntimeContainerSpec`
3. Runtime acquires provider session, registers, and leases to the trial
4. After trial completion, releases the lease
5. Default policy: destroy containers on release (no warm reuse)
6. Run-end cleanup barrier ensures no leaked containers

Override with `--keep-containers` or `--keep-failed-containers`.

---

## Retry and recovery

| Layer | Scope | Mechanism |
|-------|-------|-----------|
| HTTP retry | Individual API call | Exponential backoff in `OpenAICompatibleChatClient` |
| Deferred auto retry | Within a run | `recovery_queue` with configurable backoff |
| Manual retry | Across runs | `snowl retry <run_id>` |

---

## Observability

Run artifacts written under `.snowl/runs/<run_id>/`:

| File | Content |
|------|---------|
| `manifest.json` | Run metadata (project, models, timestamps) |
| `plan.json` | Trial plan (task × agent × sample matrix) |
| `events.jsonl` | Stream of all runtime events |
| `outcomes.json` | Final outcomes for all trials |
| `aggregate.json` | Per (task, agent) metric averages |
| `metrics_wide.csv` | Flat CSV of all metrics |
| `profiling.json` | Runtime profiling data |
| `runtime_state.json` | Current run state |
| `recovery.json` | Recovery ledger |
| `run.log` | Human-readable log |

The web monitor reads these artifacts for live and historical views.

---

## Internal boundaries

These are internal APIs, not yet public extension points:

- `EvalSpec` — normalized run inputs
- `PlanBuilder` — trial planning
- `RuntimePolicy` — runtime budgets
- `RunArtifactStore` — artifact contracts
- `RunEventBus` — observability
- `RecoveryManager` — retry ledgers
- `EvalTrialLifecycle` — one-trial execution side effects
- `ToolMiddleware` — composable tool call/result interception

These boundaries stabilize code organization but do not yet define plugin or
YAML v2 contracts.
