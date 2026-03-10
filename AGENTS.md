# Snowl Agent Instructions

This repository is an agent evaluation framework, not just a benchmark collection.
When working here, optimize for correctness of evaluation contracts, runtime reliability, reproducibility, and observability before adding surface-level features.

## What Snowl Is

Snowl's core unit is `Task x AgentVariant x Sample`, with one active `Scorer` evaluating each trial.
The framework currently has three major layers:

1. Contract and execution core
   Files: `snowl/core/`, `snowl/runtime/`, `snowl/eval.py`, `snowl/bench.py`
2. Benchmark adaptation and scoring
   Files: `snowl/benchmarks/`, `snowl/scorer/`, `examples/`
3. Observability and UX
   Files: `snowl/ui/`, `snowl/web/`, `webui/`, `snowl/_webui/`

## Source Of Truth

Prefer these sources when reasoning about behavior:

1. `START_HERE.md`
2. `PLANS.md`
3. `README.md`
4. `DESIGN.md`
5. Code and tests

If docs and code disagree, trust the code, then update the docs.

## Critical Repo Rules

1. Treat `webui/` as the editable source for the Next.js monitor.
2. Treat `snowl/_webui/` as the packaged mirror used for distribution.
3. Do not hand-edit build artifacts inside `snowl/_webui/.next/`, `webui/.next/`, `build/`, or `dist/`.
4. Do not modify `references/` contents unless the task is explicitly about benchmark references.
5. Do not commit `.snowl/` run artifacts, logs, caches, or local benchmark outputs.
6. Prefer improving platform contracts and diagnostics over adding one-off benchmark hacks.

## Architecture Map

### Contracts

- `snowl/core/task.py`: task and task-provider contracts
- `snowl/core/agent.py`: agent runtime contract
- `snowl/core/agent_variant.py`: variant binding / compare semantics
- `snowl/core/task_result.py`: normalized trial result contract
- `snowl/core/scorer.py`: score contract and validation
- `snowl/core/tool.py`: tool and env-op compatibility

### Execution

- `snowl/eval.py`: autodiscovery, plan expansion, artifact writing
- `snowl/runtime/engine.py`: trial execution loop
- `snowl/runtime/container_runtime.py`: task-specific container lifecycle
- `snowl/runtime/resource_scheduler.py`: concurrency governance
- `snowl/envs/`: sandbox, local, terminal, GUI environments

### Benchmarks

- `snowl/benchmarks/registry.py`: adapter registration
- `snowl/benchmarks/*/adapter.py`: benchmark-to-task mapping
- `snowl/benchmarks/*/scorer.py`: benchmark-specific scoring

### Observability

- `snowl/ui/contracts.py`: normalized live event and task-monitor state
- `snowl/web/monitor.py`: run discovery, event ingestion, snapshot/index logic
- `snowl/web/runtime.py`: embedded Next runtime bootstrap
- `webui/`: Next.js monitor source

## How To Approach Work

### If the task is about eval behavior

Start with:

1. `snowl/eval.py`
2. `snowl/runtime/engine.py`
3. Relevant `tests/test_eval_*`, `tests/test_runtime_*`

### If the task is about benchmark behavior

Start with:

1. `snowl/bench.py`
2. `snowl/benchmarks/registry.py`
3. The specific adapter and scorer under `snowl/benchmarks/<name>/`
4. Matching benchmark tests

### If the task is about monitoring or Web UI

Start with:

1. `snowl/web/monitor.py`
2. `snowl/web/runtime.py`
3. `webui/src/`
4. Then sync intentional source changes into `snowl/_webui/` if packaging requires it

## Verification Expectations

Run the smallest credible validation for the area you changed.

Common checks:

- Python unit tests: `pytest -q`
- Eval/runtime focused: `pytest -q tests/test_eval_autodiscovery.py tests/test_runtime_engine.py tests/test_cli_eval.py`
- Web monitor focused: `pytest -q tests/test_web_monitor_store.py tests/test_web_runtime.py tests/test_eval_web_observability.py`
- Web UI focused: `cd webui && npm run -s typecheck`
- Packaging sanity: `pip install -e .`

If a change touches both Python runtime and Web monitor contracts, validate both layers.

## What Good Changes Look Like

1. Preserve strict normalized contracts between runtime, aggregator, and UI.
2. Improve artifacts and logs in a way that helps benchmark debugging later.
3. Avoid benchmark-specific branching in shared UI unless the shared contract is extended first.
4. Keep the CLI entrypoint simple while moving complexity into reusable runtime layers.
5. Prefer incremental, test-backed improvements over large rewrites.

## What To Avoid

1. Do not treat Snowl as a single-benchmark wrapper.
2. Do not hardcode assumptions that every task is QA-only or container-only.
3. Do not let UI needs leak malformed state back into runtime contracts.
4. Do not add parallel systems if an existing contract can be extended cleanly.
5. Do not edit generated files to make tests or UI "look right".

## Documentation Rule

Any substantial change to architecture, workflow, packaging, observability, or Codex workflow should update at least one of:

- `START_HERE.md`
- `PLANS.md`
- `README.md`
- `docs/codex_best_practices.md`
