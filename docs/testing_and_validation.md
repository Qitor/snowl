# Testing And Validation

This file collects concrete commands and the minimum expected checks for common change types.

## Baseline Setup

From the repo root:

```bash
pip install -e .
```

If you touch the web monitor:

```bash
cd webui && npm run -s typecheck
```

## Targeted Python Test Commands

### Eval / Runtime

```bash
pytest -q tests/test_eval_autodiscovery.py tests/test_runtime_engine.py tests/test_resource_scheduler.py tests/test_cli_eval.py
```

### Runtime Controls / Observability

```bash
pytest -q tests/test_runtime_controls_and_profiling.py tests/test_eval_web_observability.py tests/test_web_monitor_store.py tests/test_web_runtime.py
```

### Benchmark Registry / Adapter Coverage

```bash
pytest -q tests/test_benchmark_registry_and_cli.py tests/test_strongreject_benchmark.py tests/test_terminalbench_benchmark.py tests/test_osworld_benchmark.py tests/test_toolemu_benchmark.py tests/test_agentsafetybench_benchmark.py
```

### Agents / Models / Scorers

```bash
pytest -q tests/test_agent_contracts.py tests/test_chat_agent.py tests/test_react_agent.py tests/test_model_openai_compatible.py tests/test_scorer_contracts.py tests/test_scorer_library.py
```

### Full Suite

```bash
pytest -q
```

## Local Eval Commands

### Custom local project

```bash
snowl eval /absolute/path/to/project.yml
```

### Official examples

```bash
snowl eval examples/strongreject-official/project.yml
snowl eval examples/terminalbench-official/project.yml
snowl eval examples/osworld-official/project.yml
snowl eval examples/toolemu-official/project.yml
snowl eval examples/agentsafetybench-official/project.yml
```

### Benchmark adapter path

```bash
snowl bench list
snowl bench run terminalbench --project examples/terminalbench-official/project.yml --split test
```

### Retry path

```bash
snowl retry <run_id> --project /absolute/path/to/project.yml
```

## What To Inspect After A Run

Primary artifacts:

- `.snowl/runs/<run_id>/manifest.json`
- `.snowl/runs/<run_id>/plan.json`
- `.snowl/runs/<run_id>/summary.json`
- `.snowl/runs/<run_id>/aggregate.json`
- `.snowl/runs/<run_id>/profiling.json`
- `.snowl/runs/<run_id>/runtime_state.json`
- `.snowl/runs/<run_id>/events.jsonl`
- `.snowl/runs/<run_id>/trials.jsonl`
- `.snowl/runs/<run_id>/metrics_wide.csv`
- `.snowl/runs/<run_id>/run.log`

Recovery and diagnostics:

- `.snowl/runs/<run_id>/recovery.json`
- `.snowl/runs/<run_id>/attempts.jsonl`
- `.snowl/runs/<run_id>/diagnostics_index.json`
- `.snowl/runs/<run_id>/diagnostics/`

## Done Criteria

### Runtime Change

A runtime change is not done until:

- focused runtime tests pass
- the relevant run artifacts look correct
- event/profiling/runtime-state outputs still make sense
- docs are updated if task routing or current-state expectations changed

### Benchmark Adapter Change

A benchmark adapter change is not done until:

- registry and benchmark tests pass
- sample ids and metadata are stable
- scorer outputs remain normalized
- example commands still make sense if user-facing behavior changed

### Agent / Scorer Change

A model/agent/scorer change is not done until:

- contract tests pass
- model/provider assumptions still match `project.yml`
- emitted usage/status fields still produce valid `TaskResult` and score outputs

### Web Monitor Change

A web change is not done until:

- Python-side monitor/runtime tests pass
- `cd webui && npm run -s typecheck` passes
- any required source sync into `snowl/_webui/` is handled intentionally

### Docs-Only Change

A docs-only change is done when:

- commands, file paths, and subsystem ownership match the repo
- outdated docs are marked or corrected rather than silently contradicted
- no code changes were required for the documentation to stay truthful
