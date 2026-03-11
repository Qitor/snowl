# Snowl Development Plans

This file is the living roadmap for `snowl`.
It is intended to be useful both for humans and for coding agents executing scoped tasks.

## Product Direction

Snowl should evolve from "a repo that can run several agent benchmarks" into "a stable, extensible, observable agent evaluation platform."

That means the long-term priorities are:

1. stronger evaluation contracts
2. more reliable runtime orchestration
3. experiment-level comparison across agents, variants, models, and benchmarks
4. operator-grade observability and diagnostics
5. easier external extension by users and benchmark authors

## Phase 0: Stabilize The Core Platform

Status: in progress

Why this phase matters:
The framework already covers many benchmark types, but the shared platform layer still needs hardening so future benchmarks and UI work do not become one-off patches.

Goals:

1. Keep `Task`, `Agent`, `Scorer`, `TaskResult`, and event contracts strict and documented.
2. Improve artifact schema stability so downstream tooling can rely on it.
3. Reduce drift between runtime behavior, README claims, and Web monitor behavior.
4. Keep editable install, packaged Web UI, and CLI startup behavior predictable.

Concrete work:

- document run artifact contract and experiment identity
- standardize event schema and phase semantics
- reduce duplicated source-of-truth areas between `webui/` and `snowl/_webui/`
- strengthen smoke tests for `snowl eval`, `snowl bench run`, and monitor startup
- finish the YAML-first `project.yml` entrypoint across official examples and docs
- remove user-facing env-driven provider/benchmark knobs in favor of explicit project config

Exit criteria:

- key contracts are explicitly documented
- main local workflows are reproducible from docs
- Web monitor startup/install path is deterministic

## Phase 1: Experiment Management And Comparison

Status: next major platform milestone

Why this phase matters:
The main strategic advantage of Snowl is not only running trials, but comparing them cleanly across dimensions.

Goals:

1. Make `experiment_id` a true first-class organizing primitive.
2. Support clearer `agent x benchmark`, `agent x model`, and `benchmark x scorer` comparison workflows.
3. Improve aggregation outputs so they are useful for research and product decisions.

Concrete work:

- richer experiment summary schema
- first-class experiment manifests and metadata
- better ranking/comparison semantics across agents and variants
- export-friendly tables for notebooks and dashboards
- formal scorer-comparison strategy beyond "one scorer per run"

Exit criteria:

- experiment views are comparable without manual artifact stitching
- benchmark and custom-eval runs can participate in the same experiment lens
- multi-run comparison is clearly documented and testable

## Phase 2: Runtime Reliability At Scale

Status: important after experiment management

Why this phase matters:
As soon as teams use Snowl for larger sweeps, runtime issues become the real bottleneck.

Goals:

1. Improve scheduling, pooling, and backpressure behavior.
2. Make container-heavy benchmarks more diagnosable and resumable.
3. Separate build concurrency, sandbox concurrency, and model-call concurrency cleanly.

Concrete work:

- provider-aware budgets for agent and judge calls
- execute/score phase decoupling so scoring does not consume trial execution capacity
- stronger warm-pool and spec-hash reuse
- unified `snowl retry <run_id>` semantics with attempt-aware recovery history
- in-run deferred auto retry so transient non-success trials can be recovered without a second manual command
- clearer pretask and container lifecycle diagnostics
- larger-scale reliability tests and synthetic throughput baselines

Exit criteria:

- long-running matrix evals fail less often due to orchestration issues
- failures are inspectable without reading raw ad hoc logs
- rerun and resume paths are trustworthy
- runtime throughput improvements are measurable and reproducible

## Phase 3: Extensibility And Ecosystem Fit

Status: medium-term

Why this phase matters:
Snowl becomes more valuable when outside teams can bring their own agents, task providers, and scorers without deep framework surgery.

Goals:

1. Make custom task-provider and benchmark-adapter authoring easier.
2. Improve integration paths for external agent frameworks.
3. Clarify what is "core platform" versus "adapter/plugin surface."

Concrete work:

- adapter authoring guide
- extension points for agent framework wrappers
- better generic JSONL/CSV/HF task-provider paths
- plugin-style packaging guidance

Exit criteria:

- a new benchmark or agent integration can be added with minimal framework edits
- extension docs are good enough for external contributors

## Phase 4: Operator-Grade UX

Status: parallel but should not outrun contracts/runtime

Why this phase matters:
Monitoring is part of the product, not a bolt-on.

Goals:

1. Make experiment operations legible at four levels:
   overview, run matrix, task detail, pretask/runtime diagnostics
2. Support progressive disclosure across QA, terminal, and GUI tasks.
3. Preserve strict backend contracts while improving frontend usability.

Concrete work:

- stabilize run/task/trial detail contracts
- improve filter/search/drill-down UX
- add report/export workflows
- add benchmark-aware but contract-driven detail rendering

Exit criteria:

- users can move from experiment summary to a single failed task without losing context
- logs, scores, and task outputs are inspectable without raw artifact spelunking

## Codex Execution Guidance

Use this planning heuristic when assigning work to Codex:

1. A task should usually fit inside one subsystem and one verification loop.
2. For multi-hour or cross-cutting work, update this file first with a scoped plan.
3. Prefer tasks that end with a concrete observable outcome:
   passing tests, a reproducible command, a UI state, or a documented contract.

## Current Recommended Priorities

If choosing what to work on next, prefer this order:

1. contract and artifact clarity
2. experiment aggregation and comparison
3. runtime/container reliability
4. extension ergonomics
5. deeper UX polish
