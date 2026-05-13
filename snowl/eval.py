"""Eval — thin re-export facade composing discovery, dispatch, and retry.

All substantive logic lives in:
- ``snowl.discovery`` — component autodiscovery (Task, Agent, Scorer, ToolSpec)
- ``snowl.dispatch`` — trial scheduling, execution orchestration, run lifecycle
- ``snowl.retry`` — retry orchestration for previous runs

This module re-exports the public API for backward compatibility:
``from snowl.eval import run_eval, retry_run, ProjectComponents, ...``
"""

from snowl.discovery import (
    ProjectComponents,
    _build_initial_model_profile,
    _discover_tools,
    _maybe_load_project_config,
    _resolve_project_entry,
    _select_by_id,
    load_project_components,
)
from snowl.dispatch import (
    EvalRenderer,
    EvalRunBootstrap,
    EvalRunResult,
    EvalSummary,
    _build_rerun_command,
    _checkpoint_path,
    _default_experiment_id,
    _drain_interaction_inputs,
    _failed_trial_keys_from_latest_run,
    _interaction_equivalent_command,
    _latest_run_dir,
    _load_checkpoint,
    _outcome_from_serialized,
    _pid_alive,
    _prepare_run_artifacts_dir,
    _read_json_file,
    _resolve_run_dir_for_id,
    _sanitize_id_token,
    _save_checkpoint,
    _seed_task_monitor_from_serialized_outcome,
    _summarize,
    _task_monitor_rows,
    _to_serializable_outcome,
    run_eval,
    run_eval_with_components,
)
from snowl.retry import retry_run
from snowl.observability.events import derive_pretask_events as _derive_pretask_events

__all__ = [
    # Discovery
    "ProjectComponents",
    "load_project_components",
    # Dispatch
    "EvalRenderer",
    "EvalSummary",
    "EvalRunResult",
    "EvalRunBootstrap",
    "run_eval_with_components",
    "run_eval",
    # Retry
    "retry_run",
]
