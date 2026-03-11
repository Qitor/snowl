# Snowl Agent Instructions

Snowl is an evaluation framework, not a single-benchmark wrapper. Optimize for contract correctness, runtime reliability, reproducibility, and observability before adding convenience features.

## Read This First

1. `docs/project_map.md`
2. `docs/current_state.md`
3. `docs/architecture/runtime_and_scheduler.md` for runtime work
4. `README.md`, `START_HERE.md`, `PLANS.md`
5. The code and focused tests for the subsystem you are changing

If docs and code disagree, trust the code, then update the docs or call out the mismatch clearly.

## Where To Start

- Eval/bootstrap: `snowl/eval.py`
- Runtime execution: `snowl/runtime/engine.py`
- Runtime quotas/scheduler: `snowl/runtime/resource_scheduler.py`
- Container orchestration: `snowl/runtime/container_runtime.py`, `snowl/runtime/container_providers.py`
- Benchmarks: `snowl/bench.py`, `snowl/benchmarks/registry.py`, `snowl/benchmarks/*/`
- Agents/models/providers: `snowl/agents/`, `snowl/model/`, `snowl/project_config.py`
- Scorers: `snowl/scorer/`, benchmark-specific scorers under `snowl/benchmarks/*/scorer.py`
- Observability: `snowl/web/monitor.py`, `snowl/web/runtime.py`, `webui/src/`

## Repo Rules

- Edit `webui/` as the source for the Next.js monitor. Treat `snowl/_webui/` as the packaged mirror.
- Do not hand-edit generated artifacts under `webui/.next/`, `snowl/_webui/.next/`, `build/`, or `dist/`.
- Do not modify `references/` unless the task is explicitly about benchmark references.
- Do not commit `.snowl/` run artifacts, caches, or local outputs.

## Change Style

- Prefer incremental, test-backed changes over broad rewrites.
- Preserve shared runtime, artifact, and UI contracts; do not add benchmark-specific hacks to shared layers when a contract extension is cleaner.
- For runtime, scheduler, artifact-schema, or observability changes, validate with focused tests plus artifact inspection.
- Do not attempt a broad runtime rewrite without an explicit design doc or plan update in `PLANS.md` or `docs/`.

## Validation

- Full Python suite: `pytest -q`
- Eval/runtime focused: `pytest -q tests/test_eval_autodiscovery.py tests/test_runtime_engine.py tests/test_resource_scheduler.py tests/test_cli_eval.py`
- Web/observability focused: `pytest -q tests/test_web_monitor_store.py tests/test_web_runtime.py tests/test_eval_web_observability.py`
- Web UI typecheck: `cd webui && npm run -s typecheck`
- Packaging sanity: `pip install -e .`

## Docs

- Keep `AGENTS.md` short and persistent; put detail in `docs/*.md`.
- Update docs when architecture, workflows, observability, packaging, or Codex task-routing guidance changes.
- If you change runtime behavior in a way future agents could misunderstand, update `docs/current_state.md` or `docs/architecture/runtime_and_scheduler.md`.
