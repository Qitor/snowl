"""Benchmark run orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from snowl.benchmarks import get_default_benchmark_registry, run_conformance
from snowl.eval import EvalRenderer, EvalRunResult, load_project_components, run_eval_with_components


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


def list_benchmarks() -> list[dict[str, str]]:
    registry = get_default_benchmark_registry()
    return [
        {"name": entry.info.name, "description": entry.info.description}
        for entry in registry.list()
    ]


async def run_benchmark(
    benchmark_name: str,
    *,
    project_path: str | Path,
    split: str,
    limit: int | None,
    benchmark_args: list[str] | None = None,
    benchmark_filters: list[str] | None = None,
    task_filter: list[str] | None = None,
    agent_filter: list[str] | None = None,
    variant_filter: list[str] | None = None,
    renderer: EvalRenderer | None = None,
    max_trials: int | None = None,
    max_sandboxes: int | None = None,
    max_builds: int | None = None,
    max_model_calls: int | None = None,
    experiment_id: str | None = None,
) -> EvalRunResult:
    registry = get_default_benchmark_registry()
    adapter_kwargs = _parse_adapter_kv(benchmark_args)
    adapter = registry.create(benchmark_name, **adapter_kwargs)

    tasks = adapter.load_tasks(
        split=split,
        limit=limit,
        filters=_parse_filter_kv(benchmark_filters),
    )

    base = Path(project_path).resolve()
    base_dir = base if base.is_dir() else base.parent
    components = load_project_components(base_dir, require_task_file=False)

    rerun_cmd = " ".join(
        [
            "snowl",
            "bench",
            "run",
            benchmark_name,
            "--project",
            str(base_dir),
            "--split",
            split,
            *(["--task", ",".join(task_filter)] if task_filter else []),
            *(["--agent", ",".join(agent_filter)] if agent_filter else []),
            *(["--variant", ",".join(variant_filter)] if variant_filter else []),
            *(["--experiment-id", str(experiment_id)] if experiment_id else []),
        ]
    )

    return await run_eval_with_components(
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
        max_trials=max_trials,
        max_sandboxes=max_sandboxes,
        max_builds=max_builds,
        max_model_calls=max_model_calls,
        experiment_id=experiment_id,
    )


def check_benchmark_conformance(
    benchmark_name: str,
    *,
    benchmark_args: list[str] | None = None,
) -> dict[str, Any]:
    registry = get_default_benchmark_registry()
    adapter = registry.create(benchmark_name, **_parse_adapter_kv(benchmark_args))
    report = run_conformance(adapter)
    return {"ok": report.ok, "checks": report.checks}
