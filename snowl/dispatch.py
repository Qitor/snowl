"""Dispatch — trial scheduling, execution orchestration, and run lifecycle management.

Framework role:
- Owns the main dispatch loop that schedules trials, manages inflight concurrency, and handles
  auto-retry scheduling.
- Provides ``run_eval_with_components`` and ``run_eval`` as the primary eval entry points.
- Manages checkpoints, artifact persistence, event bus, interaction control, and renderer coordination.

Change guardrails:
- Dispatch semantics are contract-defining for ``snowl eval`` behavior.
- When changing scheduler interactions, validate both tests and generated run artifacts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from snowl.aggregator import (
    RESULT_SCHEMA_URI,
    RESULT_SCHEMA_VERSION,
    aggregate_outcomes,
)
from snowl.artifacts import RunArtifactStore
from snowl.core import (
    Agent,
    Scorer,
    Task,
    ToolSpec,
)
from snowl.discovery import (
    _build_initial_model_profile,
    _resolve_project_entry,
    _select_by_id,
    load_project_components,
)
from snowl.errors import SnowlValidationError
from snowl.envs import WarmPoolSandboxRuntime
from snowl.envs.terminal_env import set_compose_build_slot_factory
from snowl.eval_loop import EvalTrialLifecycle
from snowl.eval_spec import EvalSpec
from snowl.model import OpenAICompatibleChatClient
from snowl.observability.events import (
    RunEventBus,
    count_existing_events,
)
from snowl.planning import EvalPlan, PlanBuilder, PlanTrial, trial_key as make_trial_key, trial_models
from snowl.project_config import (
    ProjectConfig,
    ProjectRecoveryConfig,
)
from snowl.runtime import TrialOutcome
from snowl.runtime.container_lifecycle import RuntimeContainerLifecycleManager
from snowl.runtime.policy import RuntimePolicy, benchmark_name_for_task
from snowl.runtime.recovery import RecoveryManager, recovery_retry_allowed
from snowl.runtime.resource_scheduler import ResourceScheduler
from snowl.runtime.results import outcome_from_serialized, to_serializable_outcome
from snowl.ui.contracts import TaskMonitor, normalize_ui_event
from snowl.ui.input import StdinInputPump


# ---------------------------------------------------------------------------
# Protocol and data classes
# ---------------------------------------------------------------------------

class EvalRenderer(Protocol):
    def render_plan(self, plan: "EvalPlan") -> None: ...

    def render_global(self, *, done: int, total: int, success: int, incorrect: int, other: int) -> None: ...

    def render_trial_start(self, trial: "PlanTrial", index: int, total: int) -> None: ...

    def render_trial_finish(self, outcome: TrialOutcome) -> None: ...

    def render_compare(self, aggregate: Any) -> None: ...

    def render_controls(self) -> None: ...

    def render_runtime_event(self, event: dict[str, Any]) -> None: ...

    def render_summary(self, summary: "EvalSummary", artifacts_dir: str, rerun_cmd: str) -> None: ...


@dataclass(frozen=True)
class EvalSummary:
    total: int
    success: int
    incorrect: int
    error: int
    limit_exceeded: int
    cancelled: int


@dataclass(frozen=True)
class EvalRunResult:
    outcomes: list[TrialOutcome]
    plan: EvalPlan
    summary: EvalSummary
    artifacts_dir: str
    rerun_command: str


@dataclass(frozen=True)
class EvalRunBootstrap:
    run_id: str
    experiment_id: str
    benchmark: str
    artifacts_dir: str
    log_path: str
    task_count: int
    agent_count: int
    variant_count: int
    sample_count: int
    total_trials: int


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _checkpoint_path(base_dir: Path, checkpoint_key: str) -> Path:
    return base_dir / ".snowl" / "checkpoints" / f"{checkpoint_key}.json"


def _load_checkpoint(base_dir: Path, checkpoint_key: str) -> dict[str, Any]:
    path = _checkpoint_path(base_dir, checkpoint_key)
    if not path.exists():
        return {"completed": {}, "failed_keys": [], "meta": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_checkpoint(base_dir: Path, checkpoint_key: str, data: dict[str, Any]) -> None:
    path = _checkpoint_path(base_dir, checkpoint_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _latest_run_dir(base_dir: Path) -> Path | None:
    runs_dir = base_dir / ".snowl" / "runs"
    if not runs_dir.exists():
        return None
    candidates = [
        p
        for p in runs_dir.iterdir()
        if p.is_dir() and p.name != "by_run_id" and ((p / "manifest.json").exists() or (p / "outcomes.json").exists())
    ]
    if not candidates:
        return None
    return sorted(candidates)[-1]


def _failed_trial_keys_from_latest_run(base_dir: Path) -> set[str]:
    latest = _latest_run_dir(base_dir)
    if latest is None:
        return set()
    outcomes_file = latest / "outcomes.json"
    if not outcomes_file.exists():
        return set()
    rows = json.loads(outcomes_file.read_text(encoding="utf-8"))
    failed_status = {"error", "limit_exceeded", "cancelled"}
    out: set[str] = set()
    for row in rows:
        tr = row.get("task_result", {})
        status = tr.get("status")
        if status in failed_status:
            sample_token = tr.get("sample_id")
            if sample_token is None:
                # For old runs without sample_id, skip precise mapping.
                continue
            variant_id = "default"
            payload = tr.get("payload") or {}
            if isinstance(payload, dict):
                variant_id = str(payload.get("variant_id") or "default")
            out.add(f"{tr.get('task_id')}::{tr.get('agent_id')}::{variant_id}::{sample_token}")
    return out


# ---------------------------------------------------------------------------
# Summary and serialization helpers
# ---------------------------------------------------------------------------

def _summarize(outcomes: list[TrialOutcome]) -> EvalSummary:
    counts = {"success": 0, "incorrect": 0, "error": 0, "limit_exceeded": 0, "cancelled": 0}
    for o in outcomes:
        counts[o.task_result.status.value] += 1

    return EvalSummary(
        total=len(outcomes),
        success=counts["success"],
        incorrect=counts["incorrect"],
        error=counts["error"],
        limit_exceeded=counts["limit_exceeded"],
        cancelled=counts["cancelled"],
    )


def _task_monitor_rows(task_monitor: TaskMonitor, *, model_by_trial_key: dict[str, str | None] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "task_id": state.task_id,
            "agent_id": state.agent_id,
            "variant_id": state.variant_id,
            "sample_id": state.sample_id,
            "model": (model_by_trial_key or {}).get(state.key),
            "status": state.status.value,
            "step_count": state.step_count,
            "duration_ms": state.duration_ms,
            "latest_action": state.latest_action,
            "latest_observation": state.latest_observation,
            "latest_message": state.latest_message,
            "scorer_metrics": dict(state.scorer_metrics),
        }
        for state in task_monitor.list_states()
    ]


def _seed_task_monitor_from_serialized_outcome(task_monitor: TaskMonitor, row: dict[str, Any]) -> None:
    task_result = dict(row.get("task_result") or {})
    payload = dict(task_result.get("payload") or {})
    timing = dict(task_result.get("timing") or {})
    scores = dict(row.get("scores") or {})
    scorer_metrics = {
        str(metric): float(value.get("value") or 0.0)
        for metric, value in scores.items()
        if isinstance(value, dict) and isinstance(value.get("value"), (int, float))
    }
    task_monitor.seed_state(
        task_id=str(task_result.get("task_id") or "-"),
        agent_id=str(task_result.get("agent_id") or "unknown"),
        variant_id=str(payload.get("variant_id") or "default"),
        sample_id=(str(task_result.get("sample_id")) if task_result.get("sample_id") is not None else None),
        status=str(task_result.get("status") or "queued"),
        started_at_ms=(int(timing.get("started_at_ms")) if timing.get("started_at_ms") is not None else None),
        ended_at_ms=(int(timing.get("ended_at_ms")) if timing.get("ended_at_ms") is not None else None),
        duration_ms=(int(timing.get("duration_ms")) if timing.get("duration_ms") is not None else None),
        latest_message=str((task_result.get("error") or {}).get("message") or "") or None,
        scorer_metrics=scorer_metrics,
    )


def _to_serializable_outcome(outcome: TrialOutcome) -> dict[str, Any]:
    return to_serializable_outcome(
        outcome,
        schema_version=RESULT_SCHEMA_VERSION,
        schema_uri=RESULT_SCHEMA_URI,
    )


def _outcome_from_serialized(row: dict[str, Any]) -> TrialOutcome:
    return outcome_from_serialized(row)


def _read_json_file(path: Path, *, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _resolve_run_dir_for_id(base_dir: Path, run_id: str) -> Path:
    pointer = base_dir / ".snowl" / "runs" / "by_run_id" / run_id
    if pointer.exists() or pointer.is_symlink():
        try:
            if pointer.is_symlink():
                return pointer.resolve()
            raw = pointer.read_text(encoding="utf-8").strip()
            if raw:
                target = Path(raw)
                return target if target.is_absolute() else (pointer.parent / target).resolve()
        except Exception:
            pass
    direct = base_dir / ".snowl" / "runs" / run_id.removeprefix("run-")
    if direct.exists():
        return direct.resolve()
    raise SnowlValidationError(f"Run not found for retry: {run_id}")


def _pid_alive(pid: int | None) -> bool:
    if pid is None or int(pid) <= 0:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# Artifact and command helpers
# ---------------------------------------------------------------------------

def _prepare_run_artifacts_dir(*, base_dir: Path, run_id: str) -> Path:
    runs_root = base_dir / ".snowl" / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    stamp = run_id[4:] if run_id.startswith("run-") else datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = runs_root / stamp
    if out_dir.exists():
        idx = 1
        while True:
            candidate = runs_root / f"{stamp}-{idx:02d}"
            if not candidate.exists():
                out_dir = candidate
                break
            idx += 1
    out_dir.mkdir(parents=True, exist_ok=False)

    by_run_id_dir = runs_root / "by_run_id"
    by_run_id_dir.mkdir(parents=True, exist_ok=True)
    pointer = by_run_id_dir / run_id
    if pointer.exists() or pointer.is_symlink():
        try:
            pointer.unlink()
        except Exception:
            pass
    try:
        pointer.symlink_to(Path("..") / out_dir.name)
    except Exception:
        pointer.write_text(str(out_dir), encoding="utf-8")

    return out_dir


def _sanitize_id_token(value: str, *, default: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "")).strip("-").lower()
    return token or default


def _default_experiment_id(*, base_dir: Path, started_ms: int) -> str:
    ts = datetime.fromtimestamp(started_ms / 1000.0, tz=timezone.utc).strftime("%Y%m%dT%H")
    project = _sanitize_id_token(base_dir.name, default="project")
    digest = hashlib.sha1(str(base_dir).encode("utf-8")).hexdigest()[:8]
    return f"{project}-{ts}-{digest}"


def _build_rerun_command(
    entry_path: Path,
    task_filter: list[str] | None,
    agent_filter: list[str] | None,
    variant_filter: list[str] | None = None,
    scorer_filter: list[str] | None = None,
    experiment_id: str | None = None,
) -> str:
    cmd = ["snowl", "eval", str(entry_path)]
    if task_filter:
        cmd.extend(["--task", ",".join(task_filter)])
    if agent_filter:
        cmd.extend(["--agent", ",".join(agent_filter)])
    if variant_filter:
        cmd.extend(["--variant", ",".join(variant_filter)])
    if scorer_filter:
        cmd.extend(["--scorer", ",".join(scorer_filter)])
    if experiment_id:
        cmd.extend(["--experiment-id", str(experiment_id)])
    return " ".join(cmd)


def _interaction_equivalent_command(
    entry_path: Path,
    *,
    task_filter: list[str] | None,
    agent_filter: list[str] | None,
    variant_filter: list[str] | None,
    experiment_id: str | None,
    controller: Any | None,
) -> str:
    extra: list[str] = []
    if controller is not None and hasattr(controller, "to_cli_flags"):
        try:
            extra = list(controller.to_cli_flags())
        except Exception:
            extra = []
    cmd = ["snowl", "eval", str(entry_path)]
    if task_filter:
        cmd.extend(["--task", ",".join(task_filter)])
    if agent_filter:
        cmd.extend(["--agent", ",".join(agent_filter)])
    if variant_filter:
        cmd.extend(["--variant", ",".join(variant_filter)])
    if experiment_id:
        cmd.extend(["--experiment-id", str(experiment_id)])
    cmd.extend(extra)
    return " ".join(cmd)


def _drain_interaction_inputs(
    *,
    interaction_controller: Any,
    run_id: str,
    renderer: EvalRenderer | None,
    logger,
    event_sink=None,
) -> int:
    consume = getattr(interaction_controller, "consume_inputs", None)
    inputs = consume() if callable(consume) else list(getattr(interaction_controller, "queued_keys", []))
    if hasattr(interaction_controller, "queued_keys"):
        interaction_controller.queued_keys = []
    processed = 0
    for raw in inputs:
        if hasattr(interaction_controller, "handle_input"):
            action = interaction_controller.handle_input(raw)
        else:
            action = interaction_controller.handle_key(raw)
        if not action:
            continue
        evt = normalize_ui_event(
            {"event": "ui.control", "input": raw, "message": action},
            run_id=run_id,
            ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ).to_dict()
        if callable(event_sink):
            event_sink(dict(evt))
        logger(f"control {json.dumps(evt, ensure_ascii=False)}")
        if renderer and hasattr(renderer, "render_runtime_event"):
            renderer.render_runtime_event(evt)
        processed += 1
    return processed


# ---------------------------------------------------------------------------
# Main dispatch: run_eval_with_components
# ---------------------------------------------------------------------------

async def run_eval_with_components(
    *,
    entry_path: Path,
    base_dir: Path,
    tasks: list[Task],
    agents: list[Agent],
    scorer: Scorer | None = None,
    scorers: tuple = (),
    tool_specs: list[ToolSpec],
    task_filter: list[str] | None = None,
    agent_filter: list[str] | None = None,
    variant_filter: list[str] | None = None,
    scorer_filter: list[str] | None = None,
    renderer: EvalRenderer | None = None,
    rerun_command: str | None = None,
    checkpoint_key: str | None = None,
    resume: bool = False,
    rerun_failed_only: bool = False,
    interaction_controller: Any | None = None,
    max_running_trials: int | None = None,
    max_container_slots: int | None = None,
    max_builds: int | None = None,
    max_scoring_tasks: int | None = None,
    provider_budgets: dict[str, int] | None = None,
    keep_containers: bool = False,
    keep_failed_containers: bool = False,
    max_trials: int | None = None,
    max_sandboxes: int | None = None,
    max_model_calls: int | None = None,
    project_config: ProjectConfig | None = None,
    experiment_id: str | None = None,
    on_run_bootstrap: Callable[[EvalRunBootstrap], None] | None = None,
    source_metadata: dict[str, Any] | None = None,
    retry_run_id: str | None = None,
    retry_run_dir: Path | None = None,
) -> EvalRunResult:
    tasks = _select_by_id(tasks, task_filter, lambda t: t.task_id)
    agents = _select_by_id(agents, agent_filter, lambda a: getattr(a, "agent_id"))
    agents = _select_by_id(agents, variant_filter, lambda a: str(getattr(a, "variant_id", "default")))

    # Filter scorers by id if scorer_filter is provided
    if scorer_filter and scorers:
        scorers = tuple(_select_by_id(list(scorers), scorer_filter, lambda s: str(getattr(s, "scorer_id", ""))))
    elif scorer_filter and scorer is not None:
        scorer_list = _select_by_id([scorer], scorer_filter, lambda s: str(getattr(s, "scorer_id", "")))
        if scorer_list:
            scorer = scorer_list[0]
        else:
            scorer = None

    if not tasks:
        raise SnowlValidationError("Task filter matched zero tasks.")
    if not agents:
        raise SnowlValidationError("Agent/variant filter matched zero agents.")

    if max_running_trials is None:
        max_running_trials = max_trials
    if max_container_slots is None:
        max_container_slots = max_sandboxes
    if provider_budgets is None and max_model_calls is not None:
        provider_budgets = {"default": max_model_calls}

    budget_resolution = RuntimePolicy().resolve(
        tasks=tasks,
        project_config=project_config,
        interaction_controller=interaction_controller,
        max_running_trials=max_running_trials,
        max_container_slots=max_container_slots,
        max_builds=max_builds,
        max_scoring_tasks=max_scoring_tasks,
        provider_budgets=provider_budgets,
    )
    budgets = budget_resolution.as_dict()
    docker_like = bool(budgets["docker_like"])
    scheduler = ResourceScheduler(**budget_resolution.to_scheduler_kwargs())
    set_compose_build_slot_factory(scheduler.build_slot)
    OpenAICompatibleChatClient.set_global_model_call_slot_resolver(
        lambda config: scheduler.provider_slot(getattr(config, "provider_id", "default"))
    )
    OpenAICompatibleChatClient.set_global_429_reporter(
        lambda provider_id: scheduler.report_429(provider_id)
    )
    OpenAICompatibleChatClient.set_global_success_reporter(
        lambda provider_id: scheduler.report_success(provider_id)
    )

    run_started = int(datetime.now(timezone.utc).timestamp() * 1000)
    retry_mode = retry_run_id is not None
    failed_only_keys: set[str] = set()
    if rerun_failed_only and not retry_mode:
        failed_only_keys = _failed_trial_keys_from_latest_run(base_dir)
        if not failed_only_keys:
            raise SnowlValidationError("No failed trials found in latest run for rerun-failed-only.")
    recovery_config = project_config.runtime.recovery if project_config is not None else ProjectRecoveryConfig()
    auto_retry_enabled = bool(recovery_config.auto_retry_non_success)
    max_auto_retries_per_trial = max(0, int(recovery_config.max_auto_retries_per_trial))
    auto_retry_backoff_ms = max(0, int(recovery_config.backoff_ms))
    run_id = str(retry_run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ"))
    if not experiment_id:
        experiment_id = _default_experiment_id(base_dir=base_dir, started_ms=run_started)
    artifacts_dir_live = (retry_run_dir.resolve() if retry_run_dir is not None else _prepare_run_artifacts_dir(base_dir=base_dir, run_id=run_id))
    live_run_log_path = artifacts_dir_live / "run.log"
    live_run_log_path.touch(exist_ok=True)
    live_events_path = artifacts_dir_live / "events.jsonl"
    # Resolve scorers: use explicit list if provided, otherwise fall back to single scorer
    _effective_scorers = scorers if scorers else ((scorer,) if scorer else ())
    plan = PlanBuilder().build(tasks, agents, scorers=list(_effective_scorers) if _effective_scorers else None)
    recovery_manager = RecoveryManager(
        run_dir=artifacts_dir_live,
        run_id=run_id,
        schema_version=RESULT_SCHEMA_VERSION,
        schema_uri=RESULT_SCHEMA_URI,
    )
    recovery = recovery_manager.state
    effective_rows = recovery_manager.effective_rows()
    if renderer:
        bench_name = None
        if tasks:
            maybe_meta = getattr(tasks[0], "metadata", {}) or {}
            if isinstance(maybe_meta, dict):
                bench_name = str(maybe_meta.get("benchmark") or maybe_meta.get("benchmark_name") or "").strip() or None
        if hasattr(renderer, "configure_panels"):
            try:
                renderer.configure_panels(benchmark_name=bench_name, project_dir=base_dir)
            except Exception:
                pass
        if interaction_controller is not None and hasattr(renderer, "bind_controller"):
            renderer.bind_controller(interaction_controller)
        renderer.render_plan(plan)
        if hasattr(renderer, "render_controls"):
            renderer.render_controls()
        if docker_like and hasattr(renderer, "render_runtime_event"):
            renderer.render_runtime_event(
                normalize_ui_event(
                    {
                        "event": "runtime.control.max_running_trials",
                        "message": "docker_default_serial",
                        "max_running_trials": budgets["max_running_trials"],
                    },
                    run_id=run_id,
                    ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
                ).to_dict()
            )

    if checkpoint_key is None:
        checkpoint_key = hashlib.sha1(
            (
                str(base_dir)
                + "|"
                + ",".join(plan.task_ids)
                + "|"
                + ",".join(plan.agent_ids)
                + f"|{plan.mode}"
            ).encode("utf-8")
        ).hexdigest()[:16]

    checkpoint = (
        _load_checkpoint(base_dir, checkpoint_key)
        if (resume and not retry_mode)
        else {"completed": {}, "in_progress": {}, "failed_keys": [], "meta": {}}
    )
    checkpoint.setdefault("completed", {})
    checkpoint.setdefault("in_progress", {})
    checkpoint.setdefault("failed_keys", [])
    checkpoint.setdefault("meta", {})

    outcomes: list[TrialOutcome] = []
    effective_outcomes_by_key: dict[str, TrialOutcome] = {}
    run_log_lines: list[str] = []
    task_monitor = TaskMonitor()
    benchmark_names = sorted({benchmark_name_for_task(task) for task in tasks})
    benchmark_hint = benchmark_names[0] if len(benchmark_names) == 1 else "mixed"
    event_bus = RunEventBus(
        events_path=live_events_path,
        runtime_state_path=artifacts_dir_live / "runtime_state.json",
        run_id=run_id,
        experiment_id=str(experiment_id),
        benchmark=benchmark_hint,
        started_ts_ms=run_started,
        schema_version=RESULT_SCHEMA_VERSION,
        initial_event_index=(count_existing_events(live_events_path) if retry_mode else 0),
    )
    artifact_store = RunArtifactStore(base_dir=base_dir, run_id=run_id, out_dir=artifacts_dir_live)

    def _log(message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        line = f"[{ts}] {message}"
        run_log_lines.append(line)
        try:
            with live_run_log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _record_event(row: dict[str, Any], *, trial: PlanTrial | None = None) -> dict[str, Any]:
        persisted_rows = event_bus.append(row, trial=trial)
        return persisted_rows[0]

    container_lifecycle = RuntimeContainerLifecycleManager(
        run_id=run_id,
        emit=lambda evt: _record_event(dict(evt)),
        keep_containers=keep_containers,
        keep_failed_containers=keep_failed_containers,
    )

    model_profile = _build_initial_model_profile(entry_path)
    model_profile_evt = normalize_ui_event(
        {
            "event": "runtime.model.profile",
            "phase": "runtime",
            **model_profile,
        },
        run_id=run_id,
        ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
    ).to_dict()
    _record_event(dict(model_profile_evt))
    _log("model_profile " + json.dumps(model_profile, ensure_ascii=False))
    if renderer and hasattr(renderer, "render_runtime_event"):
        renderer.render_runtime_event(model_profile_evt)
    completed = checkpoint.get("completed", {})
    if effective_rows:
        for key, raw in effective_rows.items():
            outcome = recovery_manager.outcome_from_attempt_row(raw)
            effective_outcomes_by_key[key] = outcome
            outcomes.append(outcome)
            _seed_task_monitor_from_serialized_outcome(
                task_monitor,
                {
                    "task_result": raw.get("task_result") or {},
                    "scores": raw.get("scores") or {},
                },
            )
    else:
        for key, raw in completed.items():
            outcome = _outcome_from_serialized(raw)
            effective_outcomes_by_key[key] = outcome
            outcomes.append(outcome)

    success = incorrect = other = 0
    for existing in outcomes:
        status = existing.task_result.status.value
        if status == "success":
            success += 1
        elif status == "incorrect":
            incorrect += 1
        else:
            other += 1

    executable_trials: list[PlanTrial] = []
    for trial in plan.trials:
        key = make_trial_key(trial)
        if retry_mode:
            effective_row = effective_rows.get(key)
            effective_status = str(((effective_row or {}).get("task_result") or {}).get("status") or "").strip().lower()
            if effective_row is not None and effective_status == "success":
                continue
        elif rerun_failed_only and key not in failed_only_keys:
            continue
        if (resume and not retry_mode) and key in completed:
            continue
        executable_trials.append(trial)

    # Apply queued interactive commands before scheduling, so UI/task filters
    # have deterministic parity with no-ui CLI flags.
    if interaction_controller is not None:
        _drain_interaction_inputs(
            interaction_controller=interaction_controller,
            run_id=run_id,
            renderer=renderer,
            logger=_log,
            event_sink=_record_event,
        )
        should_display = getattr(interaction_controller, "should_display", None)
        if callable(should_display):
            executable_trials = [
                tr
                for tr in executable_trials
                if should_display(
                    task_id=tr.task_id,
                    agent_id=tr.agent_id,
                    variant_id=tr.variant_id,
                    status=None,
                )
            ]

    for trial in executable_trials:
        task_monitor.upsert_queued(
            task_id=trial.task_id,
            agent_id=trial.agent_id,
            variant_id=trial.variant_id,
            sample_id=trial.sample_id,
        )

    total = len(plan.trials)
    manifest_extra = {}
    if source_metadata:
        manifest_extra["source"] = dict(source_metadata)
    manifest_extra["recovery"] = {
        "ledger": "recovery.json",
        "attempts_jsonl": "attempts.jsonl",
        "mode": "retry" if retry_mode else "inline",
        "auto_retry_non_success": auto_retry_enabled,
        "max_auto_retries_per_trial": max_auto_retries_per_trial,
        "backoff_ms": auto_retry_backoff_ms,
    }
    artifact_store.write_live_metadata(
        out_dir=artifacts_dir_live,
        experiment_id=str(experiment_id),
        benchmark=benchmark_hint,
        plan=plan,
        task_monitor=task_monitor,
        controls=scheduler.controls(),
        trial_count=total,
        event_stream_mode="live_append",
        manifest_extra=manifest_extra,
    )
    if on_run_bootstrap is not None:
        on_run_bootstrap(
            EvalRunBootstrap(
                run_id=run_id,
                experiment_id=str(experiment_id),
                benchmark=benchmark_hint,
                artifacts_dir=str(artifacts_dir_live),
                log_path=str(live_run_log_path),
                task_count=len(plan.task_ids),
                agent_count=len(plan.agent_ids),
                variant_count=len(plan.variant_ids),
                sample_count=plan.sample_count,
                total_trials=total,
            )
        )
    checkpoint["meta"] = {
        "run_id": run_id,
        "experiment_id": experiment_id,
        "task_ids": plan.task_ids,
        "agent_ids": plan.agent_ids,
        "variant_ids": plan.variant_ids,
        "mode": plan.mode,
        "benchmark": benchmark_hint,
        "controls": scheduler.controls(),
    }
    if resume and not retry_mode:
        _save_checkpoint(base_dir, checkpoint_key, checkpoint)

    if recovery is not None:
        recovery.setdefault("sessions", [])
        recovery_session = {
            "session_id": f"{'retry' if retry_mode else 'run'}-{run_started}",
            "started_ts_ms": run_started,
            "ended_ts_ms": None,
            "status": "running",
            "mode": "manual_retry" if retry_mode else "initial_run",
            "selected_trial_keys": sorted(make_trial_key(trial) for trial in executable_trials),
        }
        recovery["sessions"].append(recovery_session)
        recovery_manager.write()
    else:
        recovery_session = None

    if retry_mode and not executable_trials:
        summary = _summarize(outcomes)
        rerun_cmd = rerun_command or f"snowl retry {run_id}"
        event_bus.mark_completed(ts_ms=run_started)
        event_bus.close()
        artifact_store.update_manifest_status(
            artifacts_dir_live,
            status="completed",
            ended_ts_ms=run_started,
            termination_reason="completed",
        )
        if recovery_session is not None:
            recovery_session["ended_ts_ms"] = run_started
            recovery_session["status"] = "noop"
            recovery_manager.write()
        if renderer:
            renderer.render_summary(summary, str(artifacts_dir_live), rerun_cmd)
        return EvalRunResult(
            outcomes=outcomes,
            plan=plan,
            summary=summary,
            artifacts_dir=str(artifacts_dir_live),
            rerun_command=rerun_cmd,
        )

    has_sandbox_tasks = any(getattr(t.env_spec, "sandbox_spec", None) is not None for t in tasks)
    shared_sandbox_runtime = (
        scheduler.wrap_sandbox_runtime(WarmPoolSandboxRuntime())
        if has_sandbox_tasks
        else None
    )
    checkpoint_lock = asyncio.Lock()
    done_count = len(outcomes)
    display_total = max(1, len(executable_trials)) if retry_mode else max(1, total)
    input_pump = StdinInputPump(interaction_controller) if interaction_controller is not None else None
    if input_pump is not None:
        started = input_pump.start()
        if started:
            input_mode = "unknown"
            try:
                input_mode = str(input_pump.mode())
            except Exception:
                input_mode = "unknown"
            _log(f"interactive stdin input enabled (mode={input_mode})")
            if renderer and hasattr(renderer, "render_runtime_event"):
                renderer.render_runtime_event(
                    normalize_ui_event(
                        {"event": "ui.control", "message": f"interactive stdin input enabled (mode={input_mode})"},
                        run_id=run_id,
                        ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
                    ).to_dict()
                )
            _record_event(
                normalize_ui_event(
                    {"event": "ui.control", "message": f"interactive stdin input enabled (mode={input_mode})"},
                    run_id=run_id,
                    ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
                ).to_dict()
            )
        else:
            _log("interactive stdin input disabled (stdin is not a tty)")
            evt = normalize_ui_event(
                {"event": "ui.control", "message": "interactive stdin input disabled (stdin is not a tty)"},
                run_id=run_id,
                ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
            ).to_dict()
            _record_event(dict(evt))
            if renderer and hasattr(renderer, "render_runtime_event"):
                renderer.render_runtime_event(evt)

    # Use already-resolved _effective_scorers
    effective_scorers = _effective_scorers
    primary_scorer = effective_scorers[0] if effective_scorers else None

    trial_lifecycle = EvalTrialLifecycle(
        run_id=run_id,
        base_dir=base_dir,
        checkpoint_key=checkpoint_key,
        checkpoint=checkpoint,
        checkpoint_lock=checkpoint_lock,
        resume=resume,
        retry_mode=retry_mode,
        display_total=display_total,
        scorer=primary_scorer,
        scorers=effective_scorers,
        tool_specs=tool_specs,
        shared_sandbox_runtime=shared_sandbox_runtime,
        container_lifecycle=container_lifecycle,
        scheduler=scheduler,
        task_monitor=task_monitor,
        renderer=renderer,
        event_bus=event_bus,
        recovery_manager=recovery_manager,
        effective_rows=effective_rows,
        effective_outcomes_by_key=effective_outcomes_by_key,
        outcomes=outcomes,
        completed=completed,
        log=_log,
        save_checkpoint=_save_checkpoint,
        serialize_outcome=_to_serializable_outcome,
    )

    async def _bounded_run(
        trial_index: int,
        trial: PlanTrial,
        *,
        retry_source: str = "initial_run",
    ) -> tuple[int, PlanTrial, TrialOutcome, dict[str, Any]]:
        if interaction_controller is not None:
            _drain_interaction_inputs(
                interaction_controller=interaction_controller,
                run_id=run_id,
                renderer=renderer,
                logger=_log,
                event_sink=_record_event,
            )
            while interaction_controller.paused:
                _drain_interaction_inputs(
                    interaction_controller=interaction_controller,
                    run_id=run_id,
                    renderer=renderer,
                    logger=_log,
                    event_sink=_record_event,
                )
                await asyncio.sleep(0.05)
        result = await trial_lifecycle.run(trial_index, trial, retry_source=retry_source)
        return result.trial_index, result.trial, result.outcome, result.attempt_row

    interaction_stop = asyncio.Event()
    runtime_state_stop = asyncio.Event()

    async def _interaction_loop() -> None:
        if interaction_controller is None:
            return
        last_hb = 0.0
        hb_interval = 0.4
        if renderer is not None and hasattr(renderer, "heartbeat_interval_s"):
            try:
                hb_interval = float(renderer.heartbeat_interval_s())
            except Exception:
                hb_interval = 0.4
        while not interaction_stop.is_set():
            _drain_interaction_inputs(
                interaction_controller=interaction_controller,
                run_id=run_id,
                renderer=renderer,
                logger=_log,
                event_sink=_record_event,
            )
            now = datetime.now(timezone.utc).timestamp()
            if renderer is not None and hasattr(renderer, "render_runtime_event") and (now - last_hb) >= hb_interval:
                hb_evt = normalize_ui_event(
                    {"event": "ui.heartbeat", "message": "tick"},
                    run_id=run_id,
                    ts_ms=int(now * 1000),
                ).to_dict()
                _record_event(hb_evt)
                renderer.render_runtime_event(hb_evt)
                last_hb = now
            await asyncio.sleep(0.05)

    interaction_task = (
        asyncio.create_task(_interaction_loop())
        if interaction_controller is not None
        else None
    )

    async def _runtime_state_loop() -> None:
        while not runtime_state_stop.is_set():
            event_bus.heartbeat()
            await asyncio.sleep(1.0)

    runtime_state_task = asyncio.create_task(_runtime_state_loop())

    max_inflight_trials = max(
        1,
        int(budgets["max_running_trials"] or 1) + max(0, int(budgets["max_scoring_tasks"] or 0)),
    )
    fresh_queue: list[tuple[int, PlanTrial]] = list(enumerate(executable_trials, start=1))
    recovery_queue: list[dict[str, Any]] = []
    inflight: set[asyncio.Task[tuple[int, PlanTrial, TrialOutcome, dict[str, Any]]]] = set()

    def _schedule_auto_retry(*, trial_index: int, trial: PlanTrial, attempt_row: dict[str, Any]) -> None:
        if not auto_retry_enabled:
            return
        if str(recovery_config.retry_timing or "deferred").strip().lower() != "deferred":
            return
        key = make_trial_key(trial)
        if recovery_manager.auto_retry_count(key) >= max_auto_retries_per_trial:
            return
        recovery_queue.append(
            {
                "trial_index": trial_index,
                "trial": trial,
                "retry_source": "auto_retry",
                "ready_at_ms": int(datetime.now(timezone.utc).timestamp() * 1000) + auto_retry_backoff_ms,
                "supersedes_attempt_id": attempt_row.get("attempt_id"),
            }
        )
        retry_scheduled_evt = normalize_ui_event(
            {
                "event": "runtime.trial.retry.scheduled",
                "message": "auto retry scheduled",
                "retry_source": "auto_retry",
                "attempt_no": attempt_row.get("attempt_no"),
                "failure_class": attempt_row.get("failure_class"),
                "task_id": trial.task_id,
                "agent_id": trial.agent_id,
                "variant_id": trial.variant_id,
                "sample_id": trial.sample_id,
            },
            run_id=run_id,
            ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ).to_dict()
        _record_event(retry_scheduled_evt, trial=trial)
        if renderer and hasattr(renderer, "render_runtime_event"):
            renderer.render_runtime_event(retry_scheduled_evt)

    cancelled_reason: str | None = None
    container_cleanup_summary: dict[str, Any] = {}
    try:
        while fresh_queue or recovery_queue or inflight:
            while len(inflight) < max_inflight_trials:
                dispatch_item: dict[str, Any] | None = None
                if fresh_queue:
                    trial_index, trial = fresh_queue.pop(0)
                    dispatch_item = {
                        "trial_index": trial_index,
                        "trial": trial,
                        "retry_source": "initial_run",
                    }
                else:
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    ready_idx = next(
                        (idx for idx, item in enumerate(recovery_queue) if int(item.get("ready_at_ms") or 0) <= now_ms),
                        None,
                    )
                    if ready_idx is not None:
                        dispatch_item = recovery_queue.pop(ready_idx)
                if dispatch_item is None:
                    break
                inflight.add(
                    asyncio.create_task(
                        _bounded_run(
                            int(dispatch_item["trial_index"]),
                            dispatch_item["trial"],
                            retry_source=str(dispatch_item.get("retry_source") or "initial_run"),
                        )
                    )
                )

            if not inflight:
                if recovery_queue:
                    next_ready_ms = min(int(item.get("ready_at_ms") or 0) for item in recovery_queue)
                    sleep_ms = max(1, min(250, next_ready_ms - int(datetime.now(timezone.utc).timestamp() * 1000)))
                    await asyncio.sleep(sleep_ms / 1000.0)
                    continue
                break

            done_set, pending_set = await asyncio.wait(inflight, return_when=asyncio.FIRST_COMPLETED)
            inflight = set(pending_set)
            for fut in done_set:
                i, trial, outcome, attempt_row = await fut
                if recovery_retry_allowed(outcome):
                    _schedule_auto_retry(trial_index=i, trial=trial, attempt_row=attempt_row)
                status = outcome.task_result.status.value
                done_count = len(outcomes)
                success = incorrect = other = 0
                for existing in outcomes:
                    existing_status = existing.task_result.status.value
                    if existing_status == "success":
                        success += 1
                    elif existing_status == "incorrect":
                        incorrect += 1
                    else:
                        other += 1

                if renderer:
                    renderer.render_trial_finish(outcome)
                    renderer.render_global(
                        done=done_count,
                        total=total,
                        success=success,
                        incorrect=incorrect,
                        other=other,
                    )
                    if hasattr(renderer, "render_compare"):
                        renderer.render_compare(aggregate_outcomes(outcomes))
                _log(
                    f"trial_finish idx={i}/{total} task={trial.task_id} agent={trial.agent_id} variant={trial.variant_id} sample={trial.sample_id} status={status} attempt={attempt_row.get('attempt_no')} retry_source={attempt_row.get('retry_source')}"
                )
    except asyncio.CancelledError:
        cancelled_reason = "cancelled"
        raise
    except KeyboardInterrupt:
        cancelled_reason = "cancelled"
        raise
    except Exception as exc:
        cancelled_reason = f"error:{exc.__class__.__name__}"
        raise
    finally:
        interaction_stop.set()
        runtime_state_stop.set()
        if inflight:
            for task in inflight:
                task.cancel()
            await asyncio.gather(*inflight, return_exceptions=True)
            inflight.clear()
        if interaction_task is not None:
            interaction_task.cancel()
            try:
                await interaction_task
            except asyncio.CancelledError:
                pass
        runtime_state_task.cancel()
        try:
            await runtime_state_task
        except asyncio.CancelledError:
            pass
        if input_pump is not None:
            input_pump.stop()
        container_cleanup_summary = await container_lifecycle.cleanup_run(
            reason=(cancelled_reason or "run_finally"),
        )
        _log(f"container_cleanup {json.dumps(container_cleanup_summary, ensure_ascii=False)}")
        if cancelled_reason is not None:
            ended_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
            event_bus.mark_cancelled(reason=cancelled_reason, ts_ms=ended_ts)
            artifact_store.update_manifest_status(
                artifacts_dir_live,
                status="cancelled",
                ended_ts_ms=ended_ts,
                termination_reason=cancelled_reason,
            )
            if recovery_session is not None and recovery is not None:
                recovery_session["ended_ts_ms"] = ended_ts
                recovery_session["status"] = "cancelled"
                recovery_manager.write()
        event_bus.close()

    summary = _summarize(outcomes)
    rerun_cmd = rerun_command or _build_rerun_command(
        entry_path,
        task_filter,
        agent_filter,
        variant_filter,
        experiment_id=str(experiment_id),
    )
    run_ended = int(datetime.now(timezone.utc).timestamp() * 1000)
    scheduler_stats = scheduler.stats_snapshot()
    profiling = {
        "run": {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "benchmark": benchmark_hint,
        },
        "phase_timing_ms": {
            "run_total": max(0, run_ended - run_started),
        },
        "controls": scheduler.controls(),
        "scheduler": {
            **scheduler_stats,
            "auto_container_slots": budgets["auto_container_slots"],
        },
        "throughput": {
            "trial_count": len(executable_trials),
            "trials_per_sec": (
                float(len(executable_trials))
                / (max(1, run_ended - run_started) / 1000.0)
            ),
        },
        "failure_diagnostics": {
            "error": summary.error,
            "limit_exceeded": summary.limit_exceeded,
            "cancelled": summary.cancelled,
        },
        "container_cleanup": dict(container_cleanup_summary),
        "interaction": {
            "controller_state": (
                {
                    "paused": bool(getattr(interaction_controller, "paused", False)),
                    "only_failed_focus": bool(getattr(interaction_controller, "only_failed_focus", False)),
                    "group_by": str(getattr(interaction_controller, "group_by", "none")),
                    "compare_sort": str(getattr(interaction_controller, "compare_sort", "metric")),
                    "compact_mode": bool(getattr(interaction_controller, "compact_mode", False)),
                    "task_filter": list(getattr(interaction_controller, "task_filter", []) or []),
                    "agent_filter": list(getattr(interaction_controller, "agent_filter", []) or []),
                    "variant_filter": list(getattr(interaction_controller, "variant_filter", []) or []),
                    "rerun_failed_requested": bool(getattr(interaction_controller, "rerun_failed_requested", False)),
                }
                if interaction_controller is not None
                else {}
            ),
            "actions": (
                list(getattr(interaction_controller, "action_log", []))
                if interaction_controller is not None
                else []
            ),
            "equivalent_cli": _interaction_equivalent_command(
                entry_path,
                task_filter=task_filter,
                agent_filter=agent_filter,
                variant_filter=variant_filter,
                experiment_id=str(experiment_id),
                controller=interaction_controller,
            ),
        },
        "task_monitor": _task_monitor_rows(task_monitor, model_by_trial_key=trial_models(plan)),
    }
    _log(f"summary {json.dumps(summary.__dict__, ensure_ascii=False)}")
    if recovery_session is not None and recovery is not None:
        recovery_session["ended_ts_ms"] = run_ended
        recovery_session["status"] = "completed"
        recovery_manager.write()
    artifacts_dir = artifact_store.write_final(
        outcomes=outcomes,
        plan=plan,
        summary=summary,
        rerun_command=rerun_cmd,
        out_dir=artifacts_dir_live,
        run_log_lines=(None if retry_mode else run_log_lines),
        event_rows=(None if retry_mode else event_bus.event_rows),
        profiling=profiling,
        experiment_id=str(experiment_id),
        event_stream_mode="live_append",
        manifest_extra=manifest_extra,
    )
    event_bus.mark_completed(ts_ms=run_ended)
    artifact_store.update_manifest_status(
        artifacts_dir_live,
        status="completed",
        ended_ts_ms=run_ended,
        termination_reason="completed",
    )

    if renderer:
        renderer.render_summary(summary, str(artifacts_dir), rerun_cmd)

    return EvalRunResult(
        outcomes=outcomes,
        plan=plan,
        summary=summary,
        artifacts_dir=str(artifacts_dir),
        rerun_command=rerun_cmd,
    )


# ---------------------------------------------------------------------------
# Convenience wrapper: run_eval
# ---------------------------------------------------------------------------

async def run_eval(
    path: str | Path,
    *,
    task_filter: list[str] | None = None,
    agent_filter: list[str] | None = None,
    variant_filter: list[str] | None = None,
    scorer_filter: list[str] | None = None,
    renderer: EvalRenderer | None = None,
    checkpoint_key: str | None = None,
    resume: bool = False,
    rerun_failed_only: bool = False,
    interaction_controller: Any | None = None,
    max_running_trials: int | None = None,
    max_container_slots: int | None = None,
    max_builds: int | None = None,
    max_scoring_tasks: int | None = None,
    provider_budgets: dict[str, int] | None = None,
    keep_containers: bool = False,
    keep_failed_containers: bool = False,
    max_trials: int | None = None,
    max_sandboxes: int | None = None,
    max_model_calls: int | None = None,
    experiment_id: str | None = None,
    on_run_bootstrap: Callable[[EvalRunBootstrap], None] | None = None,
) -> EvalRunResult:
    entry_path = Path(path).resolve()
    base_dir, project_config, _code = _resolve_project_entry(entry_path)
    source_metadata = {
        "kind": "eval",
        "project_path": str(entry_path),
        "project_root": str(base_dir),
    }
    eval_spec = (
        EvalSpec.from_project(
            entry_path=entry_path,
            project_config=project_config,
            source_metadata=source_metadata,
        )
        if project_config is not None
        else EvalSpec.from_legacy(
            entry_path=entry_path,
            base_dir=base_dir,
            source_metadata=source_metadata,
        )
    )
    components = load_project_components(entry_path, require_task_file=True)
    return await run_eval_with_components(
        entry_path=entry_path,
        base_dir=eval_spec.base_dir,
        tasks=components.tasks,
        agents=components.agents,
        scorer=components.scorers[0] if components.scorers else None,
        scorers=tuple(components.scorers),
        tool_specs=components.tool_specs,
        task_filter=task_filter,
        agent_filter=agent_filter,
        variant_filter=variant_filter,
        scorer_filter=scorer_filter,
        renderer=renderer,
        rerun_command=_build_rerun_command(
            entry_path,
            task_filter,
            agent_filter,
            variant_filter,
            experiment_id=experiment_id,
        ),
        checkpoint_key=checkpoint_key,
        resume=resume,
        rerun_failed_only=rerun_failed_only,
        interaction_controller=interaction_controller,
        max_running_trials=max_running_trials,
        max_container_slots=max_container_slots,
        max_builds=max_builds,
        max_scoring_tasks=max_scoring_tasks,
        provider_budgets=provider_budgets,
        keep_containers=keep_containers,
        keep_failed_containers=keep_failed_containers,
        max_trials=max_trials,
        max_sandboxes=max_sandboxes,
        max_model_calls=max_model_calls,
        project_config=eval_spec.project_config,
        experiment_id=experiment_id,
        on_run_bootstrap=on_run_bootstrap,
        source_metadata=eval_spec.source_metadata,
    )
