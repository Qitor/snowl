"""Benchmark execution bridge that adapts benchmark adapters into the shared eval pipeline.

Framework role:
- Resolves benchmark adapters from registry, loads benchmark tasks, and forwards execution into `run_eval_with_components`.
- Keeps benchmark CLI mode aligned with core eval runtime behavior.

Runtime/usage wiring:
- Primary entrypoint for `snowl bench run ...` command path.
- Key top-level symbols in this file: `_parse_filter_kv`, `_parse_adapter_kv`, `list_benchmarks`, `run_benchmark`, `check_benchmark_conformance`.

Change guardrails:
- Keep benchmark-specific parsing in adapters; this file should stay orchestration-focused.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from dataclasses import asdict

from snowl.benchmarks import get_default_benchmark_registry, run_conformance
from snowl.benchmarks.external import load_external_adapter, scaffold_benchmark_adapter
from snowl.eval import EvalRenderer, EvalRunBootstrap, EvalRunResult, load_project_components, run_eval_with_components
from snowl.project_config import find_project_file, load_project_config


def _parse_filter_kv(values: list[str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in values or []:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _parse_adapter_kv(values: list[str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in values or []:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def list_benchmarks() -> list[dict[str, Any]]:
    registry = get_default_benchmark_registry()
    return [asdict(entry.info) for entry in registry.list()]


def scaffold_benchmark(name: str, *, out_dir: str | Path) -> Path:
    return scaffold_benchmark_adapter(name, out_dir=out_dir)


async def run_benchmark(
    benchmark_name: str,
    *,
    project_path: str | Path,
    split: str,
    limit: int | None,
    adapter_spec: str | None = None,
    benchmark_args: list[str] | None = None,
    benchmark_filters: list[str] | None = None,
    task_filter: list[str] | None = None,
    agent_filter: list[str] | None = None,
    variant_filter: list[str] | None = None,
    renderer: EvalRenderer | None = None,
    max_running_trials: int | None = None,
    max_container_slots: int | None = None,
    max_builds: int | None = None,
    max_scoring_tasks: int | None = None,
    provider_budgets: dict[str, int] | None = None,
    keep_containers: bool = False,
    keep_failed_containers: bool = False,
    experiment_id: str | None = None,
    on_run_bootstrap: Callable[[EvalRunBootstrap], None] | None = None,
) -> EvalRunResult:
    registry = get_default_benchmark_registry()
    adapter_kwargs = _parse_adapter_kv(benchmark_args)
    adapter = (
        load_external_adapter(adapter_spec, **adapter_kwargs)
        if adapter_spec
        else registry.create(benchmark_name, **adapter_kwargs)
    )

    tasks = adapter.load_tasks(
        split=split,
        limit=limit,
        filters=_parse_filter_kv(benchmark_filters),
    )

    base = Path(project_path).resolve()
    entry_path = find_project_file(base) or base
    project_config = load_project_config(entry_path) if entry_path.suffix.lower() in {".yml", ".yaml"} else None
    base_dir = project_config.root_dir if project_config is not None else (base if base.is_dir() else base.parent)
    components = load_project_components(entry_path, require_task_file=False)

    rerun_cmd = " ".join(
        [
            "snowl",
            "bench",
            "run",
            benchmark_name,
            *(["--adapter", str(adapter_spec)] if adapter_spec else []),
            "--project",
            str(base_dir),
            "--split",
            split,
            *(["--limit", str(limit)] if limit is not None else []),
            *sum((["--adapter-arg", str(item)] for item in (benchmark_args or [])), []),
            *sum((["--benchmark-filter", str(item)] for item in (benchmark_filters or [])), []),
            *(["--task", ",".join(task_filter)] if task_filter else []),
            *(["--agent", ",".join(agent_filter)] if agent_filter else []),
            *(["--variant", ",".join(variant_filter)] if variant_filter else []),
            *(["--experiment-id", str(experiment_id)] if experiment_id else []),
        ]
    )

    return await run_eval_with_components(
        entry_path=entry_path,
        base_dir=base_dir,
        tasks=tasks,
        agents=components.agents,
        scorer=components.scorers[0],
        tool_specs=components.tool_specs,
        task_filter=task_filter,
        agent_filter=agent_filter,
        variant_filter=variant_filter,
        renderer=renderer,
        rerun_command=rerun_cmd,
        max_running_trials=max_running_trials,
        max_container_slots=max_container_slots,
        max_builds=max_builds,
        max_scoring_tasks=max_scoring_tasks,
        provider_budgets=provider_budgets,
        keep_containers=keep_containers,
        keep_failed_containers=keep_failed_containers,
        project_config=project_config,
        experiment_id=experiment_id,
        on_run_bootstrap=on_run_bootstrap,
        source_metadata={
            "kind": "bench",
            "project_path": str(entry_path),
            "project_root": str(base_dir),
            "benchmark": benchmark_name,
            "adapter": str(adapter_spec or ""),
            "split": split,
            "limit": limit,
            "benchmark_args": adapter_kwargs,
            "benchmark_filters": _parse_filter_kv(benchmark_filters),
        },
    )


def check_benchmark_conformance(
    benchmark_name: str,
    *,
    adapter_spec: str | None = None,
    benchmark_args: list[str] | None = None,
) -> dict[str, Any]:
    registry = get_default_benchmark_registry()
    adapter_kwargs = _parse_adapter_kv(benchmark_args)
    adapter = (
        load_external_adapter(adapter_spec, **adapter_kwargs)
        if adapter_spec
        else registry.create(benchmark_name, **adapter_kwargs)
    )
    report = run_conformance(adapter)
    return {"ok": report.ok, "checks": report.checks}
