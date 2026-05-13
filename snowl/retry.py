"""Retry — re-execute failed or selected trials from a previous run.

Framework role:
- Provides ``retry_run`` to re-execute trials from a previous eval run identified by run_id.
- Handles both eval-source and bench-source retry paths.
- Validates that the target run is not still active before retrying.

Change guardrails:
- Retry semantics must preserve run identity (same run_id) and append new attempts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from snowl.discovery import (
    _resolve_project_entry,
    load_project_components,
)
from snowl.errors import SnowlValidationError
from snowl.eval_spec import EvalSpec
from snowl.dispatch import (
    EvalRenderer,
    EvalRunBootstrap,
    EvalRunResult,
    _build_rerun_command,
    _pid_alive,
    _read_json_file,
    _resolve_run_dir_for_id,
    run_eval_with_components,
)
from snowl.project_config import ProjectConfig


async def retry_run(
    run_id: str,
    *,
    project_path: str | Path = ".",
    renderer: EvalRenderer | None = None,
    interaction_controller: Any | None = None,
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
    entry_hint = Path(project_path).resolve()
    base_dir, project_config, _ = _resolve_project_entry(entry_hint)
    run_dir = _resolve_run_dir_for_id(base_dir, run_id)
    manifest = _read_json_file(run_dir / "manifest.json", default={})
    runtime_state = _read_json_file(run_dir / "runtime_state.json", default={})
    runtime_status = str(runtime_state.get("status") or manifest.get("status") or "").strip().lower()
    owner_pid = int(runtime_state.get("owner_pid") or 0) if str(runtime_state.get("owner_pid") or "").strip() else 0
    heartbeat_ts_ms = int(runtime_state.get("heartbeat_ts_ms") or 0) if str(runtime_state.get("heartbeat_ts_ms") or "").strip() else 0
    heartbeat_fresh = heartbeat_ts_ms > 0 and (int(datetime.now(timezone.utc).timestamp() * 1000) - heartbeat_ts_ms) < 15_000
    if runtime_status == "running" and (_pid_alive(owner_pid) or heartbeat_fresh):
        raise SnowlValidationError(f"Run {run_id} is still active; stop it before retrying.")
    source = dict(manifest.get("source") or {})
    source_kind = str(source.get("kind") or "eval").strip().lower()

    if source_kind == "bench":
        from snowl.benchmarks import get_default_benchmark_registry

        benchmark_name = str(source.get("benchmark") or manifest.get("benchmark") or "").strip()
        if not benchmark_name:
            raise SnowlValidationError(f"Run {run_id} is missing benchmark source metadata for retry.")
        project_entry = Path(str(source.get("project_path") or entry_hint)).resolve()
        registry = get_default_benchmark_registry()
        adapter_kwargs = dict(source.get("benchmark_args") or {})
        adapter = registry.create(benchmark_name, **adapter_kwargs)
        tasks = adapter.load_tasks(
            split=(str(source.get("split") or "test")),
            limit=(int(source["limit"]) if source.get("limit") is not None else None),
            filters=dict(source.get("benchmark_filters") or {}),
        )
        components = load_project_components(project_entry, require_task_file=False)
        eval_spec = (
            EvalSpec.from_project(
                entry_path=project_entry,
                project_config=project_config,
                source_kind="bench",
                source_metadata=source,
            )
            if project_config is not None
            else EvalSpec.from_legacy(
                entry_path=project_entry,
                base_dir=base_dir,
                benchmark=benchmark_name,
                source_kind="bench",
                source_metadata=source,
            )
        )
        rerun_command = f"snowl retry {run_id}"
        return await run_eval_with_components(
            entry_path=eval_spec.entry_path,
            base_dir=eval_spec.base_dir,
            tasks=tasks,
            agents=components.agents,
            scorer=components.scorers[0] if components.scorers else None,
            scorers=tuple(components.scorers),
            tool_specs=components.tool_specs,
            renderer=renderer,
            rerun_command=rerun_command,
            interaction_controller=interaction_controller,
            max_running_trials=max_running_trials,
            max_container_slots=max_container_slots,
            max_builds=max_builds,
            max_scoring_tasks=max_scoring_tasks,
            provider_budgets=provider_budgets,
            keep_containers=keep_containers,
            keep_failed_containers=keep_failed_containers,
            project_config=eval_spec.project_config,
            experiment_id=experiment_id or str(manifest.get("experiment_id") or run_id),
            on_run_bootstrap=on_run_bootstrap,
            source_metadata=eval_spec.source_metadata,
            retry_run_id=run_id,
            retry_run_dir=run_dir,
        )

    project_entry = Path(str(source.get("project_path") or entry_hint)).resolve()
    base_dir, project_config, _ = _resolve_project_entry(project_entry)
    components = load_project_components(project_entry, require_task_file=True)
    eval_source = source or {
        "kind": "eval",
        "project_path": str(project_entry),
        "project_root": str(base_dir),
    }
    eval_spec = (
        EvalSpec.from_project(
            entry_path=project_entry,
            project_config=project_config,
            source_metadata=eval_source,
        )
        if project_config is not None
        else EvalSpec.from_legacy(
            entry_path=project_entry,
            base_dir=base_dir,
            source_metadata=eval_source,
        )
    )
    return await run_eval_with_components(
        entry_path=eval_spec.entry_path,
        base_dir=eval_spec.base_dir,
        tasks=components.tasks,
        agents=components.agents,
        scorer=components.scorers[0],
        tool_specs=components.tool_specs,
        renderer=renderer,
        rerun_command=f"snowl retry {run_id}",
        interaction_controller=interaction_controller,
        max_running_trials=max_running_trials,
        max_container_slots=max_container_slots,
        max_builds=max_builds,
        max_scoring_tasks=max_scoring_tasks,
        provider_budgets=provider_budgets,
        keep_containers=keep_containers,
        keep_failed_containers=keep_failed_containers,
        project_config=eval_spec.project_config,
        experiment_id=experiment_id or str(manifest.get("experiment_id") or run_id),
        on_run_bootstrap=on_run_bootstrap,
        source_metadata=eval_spec.source_metadata,
        retry_run_id=run_id,
        retry_run_dir=run_dir,
    )
