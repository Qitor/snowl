# Snowl Architecture

This document describes the current architecture of `snowl` as it exists today, and the technical direction required to turn it into an industrial-grade evaluation platform.

It is intentionally implementation-oriented.
If you are about to work on runtime scheduling, container orchestration, or large-run reliability, start here.

## 1. System Boundary

Snowl is a local evaluation platform with four current product surfaces:

1. authoring surface
   - `task.py`
   - `agent.py`
   - `scorer.py`
   - `tool.py`
   - `model.yml`
2. execution surface
   - `snowl eval`
   - `snowl bench run`
3. artifact surface
   - `.snowl/runs/<run>/...`
4. observability surface
   - plain CLI progress/logging
   - Next.js Web monitor

Today, Snowl is optimized for local single-machine execution.
It is not yet a distributed scheduler.

## 2. Primary Execution Model

The current real execution unit is:

- `Task x AgentVariant x Sample`

Important nuance:

- `Task` is the evaluation target definition
- `AgentVariant` is the bound executable identity for one tested model or configuration
- `Sample` is the concrete row fed into a trial
- `Scorer` runs once per trial, but only one active scorer is supported per run today

So the actual runtime matrix is:

- planned: `Task x AgentVariant x Sample`
- conceptual future extension: `Task x AgentVariant x Scorer x Sample`

That distinction matters because a lot of roadmap work should not pretend scorer expansion is already first-class.

## 3. Main Subsystems

### 3.1 Authoring and discovery

Main code:

- `snowl/eval.py`
- `snowl/model/project_matrix.py`
- `snowl/agents/model_variants.py`
- `snowl/core/`

Responsibilities:

- discover project components from an eval folder
- load `model.yml`
- resolve provider config
- expand `agent_matrix.models` into multiple `AgentVariant`s
- validate `Task`, `Agent`, `Scorer`, and `ToolSpec`

Important contract decisions already in place:

- tested models come from `model.yml -> agent_matrix.models`
- judge/scorer model is separate from tested models
- official examples should no longer rely on global `OPENAI_MODEL` to decide the tested model

### 3.2 Planning and run bootstrap

Main code:

- `snowl/eval.py`

Responsibilities:

- filter tasks / agents / variants
- expand the execution plan
- compute `run_id`
- compute default `experiment_id`
- prepare the live artifact directory
- initialize `run.log` and live `events.jsonl`
- emit bootstrap information for CLI and Web consumers

Important current behavior:

- `events.jsonl` is live-appended during execution
- run bootstrap now happens before the monitor sidecar starts
- CLI owns the lifetime of the auto-started monitor sidecar

### 3.3 Trial execution engine

Main code:

- `snowl/runtime/engine.py`

Responsibilities:

- execute one trial from `TrialRequest`
- prepare initial agent state from the sample
- inject context metadata including `variant_id` and `model`
- route runtime events out through the event sink
- call the agent
- call the scorer
- produce `TaskResult`, `scores`, and `trace`

Important current behavior:

- container-aware tasks go through `ContainerRuntime`
- the engine emits structured events for lifecycle visibility
- trial output is normalized into a single task result contract before artifact persistence

### 3.4 Resource scheduling

Main code:

- `snowl/runtime/resource_scheduler.py`
- `snowl/eval.py`

Current scheduler model:

- `max_trials`: top-level concurrent trial count
- `max_sandboxes`: sandbox preparation capacity
- `max_builds`: container build concurrency
- `max_model_calls`: outbound model API concurrency

Implementation shape today:

- async semaphores for trials / sandboxes / model calls
- thread bounded semaphore for builds
- one local scheduler per run

This is the current control plane for runtime concurrency.
It is already useful, but still relatively shallow.

### 3.5 Container lifecycle orchestration

Main code:

- `snowl/runtime/container_runtime.py`
- `snowl/runtime/container_providers.py`
- benchmark-specific launchers under `snowl/benchmarks/*`

Responsibilities:

- resolve the right provider for a benchmark
- translate trial context into benchmark-specific container lifecycle steps
- isolate trial resources using `task_id + sample_id + variant_id`
- emit detailed pretask / env lifecycle events

Important current rule:

- container benchmark trial resources must be variant-aware
- `variant_id` is part of compose project names, log paths, and related resource naming

This is what makes multi-model TerminalBench / OSWorld runs safe.

### 3.6 Aggregation and artifacts

Main code:

- `snowl/eval.py`
- `snowl/aggregator/`

Current artifact contract per run includes at least:

- `manifest.json`
- `summary.json`
- `aggregate.json`
- `profiling.json`
- `trials.jsonl`
- `events.jsonl`
- `metrics_wide.csv`
- `run.log`

This run directory is the durable handoff boundary between execution and observability.

### 3.7 Observability

#### CLI

Main code:

- `snowl/cli.py`
- `snowl/ui/console.py`

Current behavior:

- default mode is plain CLI progress/logging in the foreground
- `--cli-ui` switches to the legacy live console UI
- auto-started Web monitor runs as a managed background sidecar

#### Web monitor

Main code:

- `webui/`
- `snowl/_webui/`
- `snowl/web/runtime.py`
- `webui/src/server/monitor.ts`

Current behavior:

- Next.js full-stack monitor
- `/` is run gallery
- `/runs/[runId]` is run workspace
- `/compare` is a secondary history/experiment view
- monitor indexes runs from `.snowl/runs/`
- monitor consumes live `events.jsonl` and run artifacts

Important repo fact:

- `webui/` is the editable source of truth
- `snowl/_webui/` is the bundled copy shipped with the package
- these two must stay in sync intentionally

## 4. Data Flow

At a high level:

```text
project folder
  -> discovery + model matrix expansion
  -> eval plan
  -> resource scheduler
  -> trial engine
  -> container runtime / model calls / scorer
  -> run artifacts + live events
  -> CLI + Web monitor
```

A more concrete view:

1. `snowl eval <path>` loads the project and builds `AgentVariant`s
2. `run_eval_with_components(...)` creates `run_id`, `experiment_id`, and artifacts directory
3. each `PlanTrial` is scheduled through `ResourceScheduler`
4. `execute_trial(...)` runs the agent/scorer and emits structured runtime events
5. artifacts are persisted continuously or at run end
6. the Web monitor indexes the run and exposes run/summary/snapshot APIs
7. the UI consumes those APIs and SSE events for live diagnosis

## 5. Current Strengths

These are already real platform strengths:

- one consistent evaluation contract across QA, terminal, and GUI tasks
- project-level multi-model authoring
- variant-aware container isolation
- run-first monitoring UX
- live structured event stream
- usable artifact model for debugging and analysis

These strengths should be preserved while scaling the runtime.

## 6. Current Architectural Constraints

These are the current boundaries and pain points that matter for future work.

### 6.1 Single-machine scheduler

All concurrency control is local to one process and one machine.
There is no distributed queue, lease system, or remote worker model yet.

### 6.2 Coarse-grained scheduling

The scheduler controls concurrency limits, but it does not yet express richer policies such as:

- benchmark-aware fairness
- per-provider quotas
- starvation prevention
- dynamic backpressure under degraded resources
- priority lanes for build-heavy vs model-heavy work

### 6.3 Limited recovery semantics

Resume and rerun-failed exist, but recovery is still mostly run-level and artifact-driven.
There is still room to improve:

- build-step recovery
- container prepare recovery
- partial trial replay guarantees
- better failure classification for automatic policy decisions

### 6.4 Duplication between runtime truth and monitor truth

The monitor reconstructs run state from artifacts and events.
That is correct for decoupling, but it means contract drift can hurt both runtime and UI quickly if not documented tightly.

### 6.5 Bundled Web UI synchronization

Because `webui/` and `snowl/_webui/` coexist, product changes can look correct in dev but stale in packaged usage if they are not synchronized and rebuilt carefully.

## 7. The Hard Next Problem: Industrial-Grade Runtime

The next truly difficult work is not another benchmark adapter.
It is making the runtime reliable, observable, and efficient under large concurrent workloads.

That means Snowl needs to evolve from “local concurrent runner with quotas” into a stronger runtime control plane.

### 7.1 Scheduling challenges

The most important runtime problems ahead are:

- separating planning from dispatch more cleanly
- making scheduling decisions resource-aware instead of just semaphore-bound
- modeling build, sandbox, model-call, and trial resources as distinct pressure sources
- introducing fairer dispatch across large matrices
- ensuring container-heavy tasks do not monopolize the whole run

### 7.2 Container-heavy benchmark challenges

Container benchmarks create the hardest reliability problems:

- slow image/build startup
- compose/container naming collisions if identity is wrong
- delayed readiness and flaky startup chains
- large log volumes
- expensive reruns when a prepare step fails late

The architecture already emits pretask/env events.
The next step is turning those events into policy, not just diagnosis.

### 7.3 Failure-domain design

Industrial-grade behavior requires clearer failure domains:

- run-level failure
- trial-level failure
- pretask/container failure
- scorer failure
- provider/API failure
- infrastructure pressure failure

Today Snowl captures many of these as events and final task statuses.
The next step is using that structure for recovery and smarter scheduling decisions.

## 8. Architectural Principles For The Next Phase

These principles should guide future runtime work.

### 8.1 Keep contracts strict at subsystem boundaries

Do not solve scheduling or UI pain by weakening artifact contracts.
The boundaries between:

- trial execution
- artifact persistence
- monitor indexing
- UI rendering

should stay explicit and typed.

### 8.2 Preserve `AgentVariant` as the core identity primitive

`AgentVariant` is not just display metadata.
It is the execution identity used for:

- model comparison
- container isolation
- artifact attribution
- run-level aggregation

Future runtime work should deepen this identity, not bypass it.

### 8.3 Prefer observable systems over opaque optimization

If a scheduling optimization makes runtime behavior harder to diagnose, it is probably too early.
We should bias toward:

- explicit events
- explicit queue states
- explicit resource counters
- explicit failure reasons

### 8.4 Keep Web monitor as an observer, not the scheduler

The current architecture is healthy in one important way:

- CLI starts work
- runtime executes work
- artifacts/events represent truth
- Web monitor observes that truth

The Web layer should stay observational unless product scope explicitly changes.

## 9. Recommended Focus Areas For Upcoming Runtime Work

If we want Snowl to become an industrial-grade product, the most leveraged architecture work is:

1. stronger scheduler model
   - richer resource accounting
   - fair dispatch
   - backpressure strategy
2. container lifecycle hardening
   - prepare/build/start/ready recovery semantics
   - stronger warm reuse where safe
3. artifact contract hardening
   - clearer manifest/schema versioning
   - tighter event semantics
4. monitor/runtime contract alignment
   - make run and task states derivable without ambiguity
5. large-run reliability testing
   - stress and failure-injection coverage for high-event, high-container runs

## 10. Practical Read Order By Problem Area

### If you are changing planning or matrix expansion

Read:

1. `snowl/eval.py`
2. `snowl/model/project_matrix.py`
3. `snowl/agents/model_variants.py`

### If you are changing runtime scheduling

Read:

1. `snowl/eval.py`
2. `snowl/runtime/resource_scheduler.py`
3. `snowl/runtime/engine.py`
4. `snowl/runtime/container_runtime.py`

### If you are changing container-heavy benchmark behavior

Read:

1. `snowl/runtime/container_providers.py`
2. benchmark-specific code under `snowl/benchmarks/`
3. relevant official example under `examples/`

### If you are changing monitor or UI

Read:

1. `webui/src/server/monitor.ts`
2. `webui/src/app/api/*`
3. `webui/src/components/*`
4. `snowl/web/runtime.py`

## 11. Bottom Line

Snowl already has the right product spine:

- strict authoring contracts
- explicit run artifacts
- variant-aware execution
- strong observability hooks

The next phase is about making the runtime worthy of that spine.

That means the center of gravity now moves to:

- scheduling
- fault isolation
- backpressure
- recovery
- large-scale reliability

This is where Snowl becomes a real industrial platform rather than just a benchmark runner.
