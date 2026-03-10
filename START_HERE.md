# Snowl Start Here

This file is the fastest way for a new contributor or coding agent to understand how to work in `snowl`.

## 1. What This Repo Does

Snowl is a general agent evaluation framework.
Its center of gravity is not a single benchmark, but a unified evaluation contract:

- define `Task`
- define `Agent`
- define `Scorer`
- run with `snowl eval ...`

The framework then handles:

- project autodiscovery
- benchmark adaptation
- runtime/container complexity
- scoring and aggregation
- live monitoring and artifacts

## 2. Read Order

Read these in order before large changes:

1. `AGENTS.md`
2. `PLANS.md`
3. `README.md`
4. `ARCHITECTURE.md`
5. `DESIGN.md`
6. The code files relevant to your area

## 3. Repo Map

### Core framework

- `snowl/core/`
- `snowl/eval.py`
- `snowl/runtime/`
- `snowl/envs/`

### Benchmarks and scorers

- `snowl/benchmarks/`
- `snowl/scorer/`
- `examples/`
- `references/`

### Monitoring and UI

- `snowl/ui/`
- `snowl/web/`
- `webui/`
- `snowl/_webui/`

### Validation and packaging

- `tests/`
- `pyproject.toml`
- `setup.py`

## 4. Current Product Shape

Today Snowl already supports:

- custom eval folders with autodiscovery
- project-level `model.yml` authoring with `provider + agent_matrix + optional judge`
- built-in benchmark adapters
- trial execution with environment/runtime abstraction
- artifact generation under `.snowl/runs/`
- experiment summaries and aggregation
- plain CLI foreground progress with embedded Next.js Web monitoring

The current platform is strongest at local single-machine evaluation with strong observability.

## 5. Where To Start By Task Type

### New benchmark adapter or benchmark bug

Read:

1. `snowl/bench.py`
2. `snowl/benchmarks/registry.py`
3. the target adapter under `snowl/benchmarks/<name>/`
4. benchmark-specific tests in `tests/`

### Runtime, concurrency, or artifacts

Read:

1. `snowl/eval.py`
2. `snowl/runtime/engine.py`
3. `snowl/runtime/resource_scheduler.py`
4. `snowl/runtime/container_runtime.py`

### UI, events, or web monitor

Read:

1. `snowl/ui/contracts.py`
2. `snowl/web/runtime.py`
3. `webui/src/server/monitor.ts`
4. `webui/src/`

## 6. Common Commands

Install editable package:

```bash
pip install -e .
```

Run a local example:

```bash
snowl eval examples/strongreject-official
```

List benchmark adapters:

```bash
snowl bench list
```

Run a benchmark example:

```bash
snowl bench run terminalbench --project examples/terminalbench-official --split test
```

Run Python tests:

```bash
pytest -q
```

Typecheck the monitor UI:

```bash
cd webui
npm run -s typecheck
```

## 7. Important Mental Model

Snowl should keep moving toward a real evaluation platform with four durable layers:

1. authoring contracts
2. execution/runtime reliability
3. experiment aggregation and comparability
4. operator-grade observability

If a proposed change only helps one benchmark in one place but weakens a shared contract, it is usually the wrong change.

## 8. Current Sharp Edges

These are important to remember while working:

1. `webui/` and `snowl/_webui/` can diverge if changes are not synced intentionally.
2. Benchmark references live outside the package and are required for several official examples.
3. The repo has broad test coverage, but some workflows still depend on local Docker, Node, and reference repos.
4. Multi-benchmark comparison is still implemented as experiment-level aggregation across runs, not one giant unified scheduler.
5. Official multi-model authoring now flows through `model.yml` plus `build_model_variants(...)`; do not reintroduce env-driven tested-model selection.

## 9. Documentation To Maintain

If you change platform behavior, keep these current:

- `README.md`
- `README.zh-CN.md`
- `AGENTS.md`
- `PLANS.md`
- `docs/codex_best_practices.md`
