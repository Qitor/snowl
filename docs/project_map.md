# Project Map

This file is the quickest repo navigation map for humans and coding agents. It describes the codebase as it exists now.

## Top Level

- `snowl/`
  - Main Python package. Most coding tasks start here.
- `tests/`
  - Focused unit and integration coverage. Use this to confirm real behavior before trusting docs.
- `examples/`
  - Example projects that exercise official benchmark flows and custom authoring patterns.
- `docs/`
  - Repo documentation. Use this before reading large amounts of code.
- `webui/`
  - Editable Next.js monitor source.
- `snowl/_webui/`
  - Packaged mirror of the web UI used for distribution.
- `references/`
  - External benchmark/reference repos checked out locally. Usually read-only for Snowl tasks.
- `scripts/`
  - Utility scripts and throughput/reliability benchmarks.

## Python Package Map

### Contracts and Project Loading

- `snowl/core/`
  - Core contracts: `Task`, `Agent`, `AgentVariant`, `Scorer`, `TaskResult`, `ToolSpec`, env/tool compatibility.
- `snowl/project_config.py`
  - `project.yml` loader and validation.
- `snowl/eval.py`
  - Eval entrypoint, discovery, plan expansion, artifact writing, recovery, and the main scheduling loop.

### Runtime Logic

- `snowl/runtime/engine.py`
  - Trial phases: prepare, execute, score, finalize.
- `snowl/runtime/resource_scheduler.py`
  - Runtime budgets and concurrency primitives.
- `snowl/runtime/container_runtime.py`
  - Benchmark-specific container prepare/finalize wrapper.
- `snowl/runtime/container_providers.py`
  - TerminalBench and OSWorld provider implementations.
- `snowl/envs/`
  - Local, terminal, GUI, and sandbox runtime abstractions.

### Benchmark Adapters

- `snowl/bench.py`
  - `snowl bench` orchestration.
- `snowl/benchmarks/registry.py`
  - Adapter registration.
- `snowl/benchmarks/<name>/adapter.py`
  - Benchmark-to-Task mapping.
- `snowl/benchmarks/<name>/scorer.py`
  - Benchmark-specific scoring.
- Built-in adapters now:
  - `strongreject`
  - `terminalbench`
  - `osworld`
  - `toolemu`
  - `agentsafetybench`
  - `jsonl`
  - `csv`

### Agents, Models, and Providers

- `snowl/agents/chat_agent.py`
  - Built-in single-call baseline agent.
- `snowl/agents/react_agent.py`
  - Built-in ReAct baseline with tool use.
- `snowl/agents/model_variants.py`
  - Expands `agent_matrix.models` into `AgentVariant`s.
- `snowl/model/openai_compatible.py`
  - Only built-in provider client today. Handles HTTP retries and provider slot acquisition.
- `snowl/model/project_matrix.py`
  - Project model/provider helpers used by variant builders.

### Scoring and Aggregation

- `snowl/scorer/`
  - Shared scorer helpers and model-as-judge utilities.
- `snowl/aggregator/summary.py`
  - Run-level aggregation into matrix summaries.

### Observability and Operator UX

- `snowl/cli.py`
  - CLI commands, web monitor bootstrap, UI flags.
- `snowl/ui/`
  - Console renderers and normalized UI event contracts.
- `snowl/web/monitor.py`
  - Python-side run discovery and live event indexing.
- `snowl/web/runtime.py`
  - Web UI source resolution, `npm ci`, and build bootstrap.
- `webui/src/`
  - Editable Next.js monitor implementation.

## Tests and Examples

- `tests/test_eval_*`
  - Eval planning, artifacts, and live observability.
- `tests/test_runtime_*`
  - Runtime engine, controls, profiling, and scheduler behavior.
- `tests/test_*_benchmark.py`
  - Adapter/scorer behavior for each benchmark.
- `tests/test_web_*`
  - Web monitor store and runtime bootstrap.
- `examples/<benchmark>-official/`
  - Example projects for benchmark flows.
- `examples/README.md`
  - Example usage overview.

## Read This First By Task Type

### Runtime or Eval Change

1. `docs/current_state.md`
2. `docs/architecture/runtime_and_scheduler.md`
3. `snowl/eval.py`
4. `snowl/runtime/engine.py`
5. `snowl/runtime/resource_scheduler.py`
6. `tests/test_runtime_engine.py`, `tests/test_resource_scheduler.py`, `tests/test_eval_web_observability.py`

### Benchmark Adapter Change

1. `snowl/bench.py`
2. `snowl/benchmarks/registry.py`
3. `snowl/benchmarks/<name>/adapter.py`
4. `snowl/benchmarks/<name>/scorer.py`
5. `examples/<name>-official/`
6. `tests/test_<name>_benchmark.py`

### Agent or Provider Change

1. `snowl/agents/`
2. `snowl/model/openai_compatible.py`
3. `snowl/project_config.py`
4. `tests/test_chat_agent.py`, `tests/test_react_agent.py`, `tests/test_model_openai_compatible.py`

### Scorer Change

1. `snowl/scorer/`
2. Relevant benchmark scorer under `snowl/benchmarks/<name>/scorer.py`
3. `tests/test_scorer_*` and benchmark-specific tests

### Web Monitor or UI Change

1. `snowl/web/monitor.py`
2. `snowl/web/runtime.py`
3. `webui/src/server/monitor.ts`
4. `webui/src/components/`
5. `tests/test_web_monitor_store.py`, `tests/test_web_runtime.py`, `tests/test_eval_web_observability.py`

### Docs-Only Change

1. `docs/current_state.md`
2. `docs/codex_task_playbook.md`
3. `AGENTS.md`
4. The relevant code/tests to verify the docs match reality
