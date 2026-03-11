# Snowl Start Here

This is the fastest orientation file for contributors and coding agents working in `snowl`.

## 1. What Snowl Is

Snowl is an agent evaluation platform built around one execution unit:

- `Task x AgentVariant x Sample`

The platform expects you to:

- define `Task`
- define `Agent`
- define `Scorer`
- declare one `project.yml`
- run with `snowl eval path/to/project.yml`

Everything else is platform machinery around that contract.

## 2. Read Order

Read these in order before large changes:

1. `AGENTS.md`
2. `PLANS.md`
3. `README.md`
4. `ARCHITECTURE.md`
5. `docs/runtime_scheduling.md`
6. code and tests for the subsystem you are changing

## 3. Repo Map

### Core framework

- `snowl/core/`
- `snowl/eval.py`
- `snowl/runtime/`
- `snowl/envs/`
- `snowl/project_config.py`

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
- `scripts/`
- `pyproject.toml`
- `setup.py`

## 4. Current Product Shape

Today Snowl supports:

- YAML-first projects via `project.yml`
- project-level model sweeps through `agent_matrix.models`
- benchmark adapters plus custom eval projects
- provider-aware runtime concurrency
- container-aware execution for terminal / GUI benchmarks
- artifacts under `.snowl/runs/`
- plain foreground CLI + background Next.js operator board
- unified run recovery via `snowl retry <run_id>`
- attempt-aware recovery ledger plus in-run deferred auto retry for non-success trials

Important observability detail:

- running runs should become visible in the Web monitor immediately
- `manifest.json`, `plan.json`, and a live `profiling.json` skeleton are written at run startup
- `events.jsonl` extends that live view with progress and trial-level state
- `runtime_state.json` is the live lifecycle contract used to distinguish active runs, explicit cancellations, and stale zombie runs
- in the run workspace, `Overview` for a running run should reflect the live mean over already-scored trials rather than waiting for final `aggregate.json`

## 5. Where To Start By Task Type

### Eval behavior / runtime / artifacts

Read:

1. `snowl/project_config.py`
2. `snowl/eval.py`
3. `snowl/runtime/engine.py`
4. `snowl/runtime/resource_scheduler.py`
5. `tests/test_eval_autodiscovery.py`
6. `tests/test_runtime_controls_and_profiling.py`

### Benchmark behavior

Read:

1. `snowl/bench.py`
2. `snowl/benchmarks/registry.py`
3. the target adapter under `snowl/benchmarks/<name>/`
4. the official example under `examples/<name>-official/`
5. matching tests under `tests/`

### Web monitor / UI

Read:

1. `snowl/web/runtime.py`
2. `webui/src/server/monitor.ts`
3. `webui/src/`
4. then sync intentional source changes into `snowl/_webui/`

## 6. Common Commands

Install editable package:

```bash
pip install -e .
```

Run an official example:

```bash
snowl eval examples/strongreject-official/project.yml
```

Run a benchmark example:

```bash
snowl bench run terminalbench --project examples/terminalbench-official/project.yml --split test
```

Recover a cancelled / zombie / partially failed run:

```bash
snowl retry run-20260311T033703Z --project examples/strongreject-official/project.yml
```

Run tests:

```bash
pytest -q
```

Typecheck monitor UI:

```bash
cd webui
npm run -s typecheck
```

## 7. Important Mental Model

Snowl is moving toward four durable platform layers:

1. authoring contracts
2. runtime reliability and scheduling
3. experiment aggregation and comparison
4. operator-grade observability

Operator UX is intentionally split into:

- `/`: running-first operator board
- `/runs/[runId]`: single-run workspace for task triage and live diagnosis

If a change only helps one benchmark but weakens a shared contract, it is usually the wrong change.

## 8. Current Sharp Edges

1. `webui/` and `snowl/_webui/` can drift if not synced intentionally.
2. Several official examples depend on external reference repos and local Docker/Node availability.
3. The runtime scheduler is now provider-aware, but warm-pool locality and blocked-group controls are still future work.
4. Multi-benchmark comparison still happens across runs rather than through one global scheduler.
5. `project.yml` is now the source of truth; do not reintroduce user-facing env-driven provider or benchmark config.

## 9. Docs To Maintain

If you change platform behavior, keep these current:

- `README.md`
- `README.zh-CN.md`
- `ARCHITECTURE.md`
- `PLANS.md`
- relevant `examples/*/README.md`
