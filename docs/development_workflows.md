# Development Workflows

This file is task-oriented. Use it to choose the smallest safe workflow for the change you are making.

## Runtime Change Safely

### Read First

1. `docs/current_state.md`
2. `docs/architecture/runtime_and_scheduler.md`
3. `docs/container_lifecycle_management.md` if the change touches benchmark containers
4. `snowl/eval.py`
5. `snowl/runtime/engine.py`
6. `snowl/runtime/resource_scheduler.py`

### Recommended Workflow

1. Confirm whether the behavior lives in the eval loop, the engine, or the scheduler API.
2. If containers are involved, confirm whether the behavior belongs to task-declared `runtime_container` metadata, provider startup/teardown, or shared runtime lifecycle ownership.
3. Do not let agents start or stop benchmark containers; extend the runtime contract instead.
4. Add or update a focused test first when possible.
5. Make the smallest contract-preserving change.
6. Run the narrowest credible runtime test subset.
7. Inspect produced artifacts, not just test output.
8. Update docs if the behavior change affects future task routing or runtime expectations.

### Minimum Validation

```bash
pytest -q tests/test_runtime_engine.py tests/test_resource_scheduler.py tests/test_eval_web_observability.py
```

If you touched runtime-owned benchmark containers, also run:

```bash
pytest -q tests/test_container_lifecycle.py tests/test_container_runtime_providers.py tests/test_terminalbench_benchmark.py tests/test_osworld_benchmark.py tests/test_runtime_controls_and_profiling.py
```

If you touched CLI/runtime/bootstrap behavior, also run:

```bash
pytest -q tests/test_cli_eval.py tests/test_eval_autodiscovery.py tests/test_runtime_controls_and_profiling.py
```

### Artifacts To Inspect

- `.snowl/runs/<run_id>/manifest.json`
- `.snowl/runs/<run_id>/plan.json`
- `.snowl/runs/<run_id>/profiling.json`
- `.snowl/runs/<run_id>/events.jsonl`
- `.snowl/runs/<run_id>/runtime_state.json`
- `.snowl/runs/<run_id>/recovery.json`
- `.snowl/runs/<run_id>/attempts.jsonl`
- `.snowl/runs/<run_id>/run.log`

## Add Or Update A Benchmark Adapter

### Read First

1. `snowl/bench.py`
2. `snowl/benchmarks/registry.py`
3. `snowl/benchmarks/base_adapter.py`
4. The target adapter and scorer
5. `tests/test_<benchmark>_benchmark.py`

### Workflow

1. Keep dataset parsing inside the adapter.
2. Normalize rows into `Task` samples with stable `id` and `metadata`.
3. Keep benchmark-specific scoring inside the benchmark scorer, not shared runtime code.
4. Register the adapter in `snowl/benchmarks/registry.py`.
5. Update or add an example project under `examples/` if the benchmark is user-facing.

### Validation

```bash
pytest -q tests/test_benchmark_registry_and_cli.py tests/test_<benchmark>_benchmark.py
```

For official benchmark examples, also run the example-specific smoke path if dependencies are available.

## Add Or Update An Agent

### Read First

1. `snowl/core/agent.py`
2. `snowl/agents/chat_agent.py` or `snowl/agents/react_agent.py`
3. `snowl/model/openai_compatible.py`
4. `snowl/agents/model_variants.py` if variants are involved

### Workflow

1. Keep author-facing contract compatibility with `Agent.run(state, context, tools=None)`.
2. Emit runtime/model events if the agent performs model calls or tool actions.
3. Preserve `agent_id`, `variant_id`, and `model` identity propagation.
4. For project-level sweeps, prefer `build_model_variants(...)` rather than inventing new matrix plumbing.

### Validation

```bash
pytest -q tests/test_agent_contracts.py tests/test_chat_agent.py tests/test_react_agent.py tests/test_model_openai_compatible.py
```

## Add Or Update A Scorer

### Read First

1. `snowl/core/scorer.py`
2. `snowl/scorer/base.py`
3. `snowl/scorer/model_judge.py` if model-as-judge is relevant
4. Relevant benchmark scorer tests

### Workflow

1. Keep scorer output normalized as `dict[str, Score]`.
2. Keep benchmark-specific metric naming in the benchmark scorer.
3. If the scorer uses model calls, verify provider-budget behavior still makes sense.
4. If the scorer changes final status behavior, check `score_trial_phase()` in `snowl/runtime/engine.py`.

### Validation

```bash
pytest -q tests/test_scorer_contracts.py tests/test_scorer_library.py
```

Add benchmark-specific tests when changing a benchmark scorer.

## Docs + Tests + Examples

When a change affects user workflows or Codex task routing:

1. Update the relevant `docs/*.md`.
2. Update `AGENTS.md` only if the rule is repo-wide and stable.
3. Update example docs if commands or assumptions changed.
4. Prefer updating stale docs explicitly instead of letting them drift.

Useful checks:

```bash
pytest -q
pip install -e .
cd webui && npm run -s typecheck
```

## Debugging Runtime Behavior

Start with the live artifacts from a small run:

```bash
snowl eval examples/strongreject-official/project.yml --max-running-trials 1 --no-web-monitor
```

Inspect these first:

- `run.log` for operator-level sequence
- `events.jsonl` for normalized runtime events
- `profiling.json` for controls, scheduler stats, and task monitor rows
- `runtime_state.json` for active/completed/cancelled state
- `recovery.json` and `attempts.jsonl` for retry behavior
- `diagnostics/` and `diagnostics_index.json` when benchmark-specific failures are involved

If debugging container-backed work:

- confirm the task/sample emits `runtime_container` metadata first
- Check pretask-derived events in `events.jsonl`
- check `profiling.json["container_cleanup"]`
- Check compose/log paths emitted by TerminalBench provider events
- Check Docker availability before blaming scheduler behavior
