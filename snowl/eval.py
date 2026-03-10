"""Evaluation auto-discovery runner used by `snowl eval` CLI."""

from __future__ import annotations

import asyncio
import csv
import importlib.util
import inspect
import json
import hashlib
import os
import re
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Protocol, TypeVar

from snowl.aggregator import (
    AGGREGATE_SCHEMA_URI,
    RESULT_SCHEMA_URI,
    RESULT_SCHEMA_VERSION,
    aggregate_outcomes,
)
from snowl.core import (
    Agent,
    AgentVariant,
    Scorer,
    Task,
    ToolSpec,
    bind_agent_variant,
    get_default_tool_registry,
    resolve_tool_spec,
    validate_agent,
    validate_agent_variant,
    validate_scorer,
    validate_task,
)
from snowl.core.declarations import Declaration, get_declaration, has_declaration
from snowl.errors import SnowlValidationError
from snowl.envs import WarmPoolSandboxRuntime
from snowl.envs.terminal_env import set_compose_build_slot_factory
from snowl.model import OpenAICompatibleChatClient
from snowl.project_config import ProjectCodeConfig, ProjectConfig, find_project_file, load_project_config
from snowl.runtime import TrialOutcome, TrialRequest, execute_trial, execute_agent_phase, score_trial_phase
from snowl.runtime.resource_scheduler import ResourceScheduler
from snowl.ui.contracts import TaskMonitor, normalize_ui_event
from snowl.ui.input import StdinInputPump


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
class PlanTrial:
    task: Task
    agent: Agent
    sample: dict[str, Any]
    task_id: str
    agent_id: str
    variant_id: str
    model: str | None
    sample_id: str | None


@dataclass(frozen=True)
class EvalPlan:
    mode: str
    task_ids: list[str]
    agent_ids: list[str]
    variant_ids: list[str]
    sample_count: int
    trials: list[PlanTrial]


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


@dataclass(frozen=True)
class ProjectComponents:
    tasks: list[Task]
    agents: list[Agent]
    scorers: list[Scorer]
    tool_specs: list[ToolSpec]


def _maybe_load_project_config(path: Path) -> ProjectConfig | None:
    project_file = find_project_file(path)
    if project_file is None:
        return None
    return load_project_config(project_file)


def _resolve_project_entry(path: str | Path) -> tuple[Path, ProjectConfig | None, ProjectCodeConfig | None]:
    resolved = Path(path).resolve()
    config = _maybe_load_project_config(resolved)
    if config is not None:
        return config.root_dir, config, config.eval.code
    base_dir = resolved if resolved.is_dir() else resolved.parent
    return base_dir, None, None


def _build_initial_model_profile(path: Path) -> dict[str, Any]:
    config = _maybe_load_project_config(path)
    if config is not None:
        model_label = config.models[0].model if len(config.models) == 1 else f"{len(config.models)} agent models"
        return {
            "provider_id": config.provider.id,
            "model": model_label,
            "base_url": config.provider.base_url,
            "models": [entry.model for entry in config.models],
            "judge_model": config.judge.model if config.judge is not None else None,
        }
    return {
        "model": "",
        "base_url": "",
    }


def _load_module(module_name: str, file_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise SnowlValidationError(f"Failed to load module from '{file_path}'.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _discovery_strict_ids_enabled() -> bool:
    return str(os.getenv("SNOWL_DISCOVERY_STRICT_IDS", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _iter_module_values(module: ModuleType) -> list[tuple[str, Any]]:
    return sorted(vars(module).items(), key=lambda item: item[0])


def _iter_decorated_values(module: ModuleType, kind: str) -> list[tuple[str, Any, Declaration]]:
    rows: list[tuple[str, Any, Declaration]] = []
    for name, value in _iter_module_values(module):
        decl = get_declaration(value)
        if decl is None or decl.kind != kind:
            continue
        rows.append((name, value, decl))
    return sorted(rows, key=lambda row: (row[2].order, row[0]))


def _resolve_declared_candidate(value: Any, kind: str) -> list[Any]:
    if kind == "task" and isinstance(value, Task):
        return [value]
    if kind == "agent" and (
        isinstance(value, AgentVariant) or callable(getattr(value, "run", None))
    ):
        return [value]
    if kind == "scorer" and callable(getattr(value, "score", None)):
        return [value]

    if callable(value):
        produced = value()
        if produced is None:
            return []
        if isinstance(produced, (list, tuple, set)):
            return list(produced)
        return [produced]

    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _discover_tasks(module: ModuleType) -> list[Task]:
    strict_ids = _discovery_strict_ids_enabled()
    tasks: list[Task] = []
    object_seen: set[int] = set()
    id_sources: dict[str, str] = {}

    for name, value, _decl in _iter_decorated_values(module, "task"):
        for item in _resolve_declared_candidate(value, "task"):
            if not isinstance(item, Task):
                raise SnowlValidationError(
                    f"Decorated task declaration '{name}' did not resolve to Task instance(s)."
                )
            validate_task(item)
            if id(item) in object_seen:
                continue
            if item.task_id in id_sources:
                raise SnowlValidationError(
                    f"Duplicate task_id '{item.task_id}' discovered between {id_sources[item.task_id]} "
                    f"and decorated declaration '{name}'."
                )
            tasks.append(item)
            object_seen.add(id(item))
            id_sources[item.task_id] = f"decorated declaration '{name}'"

    fallback_found = False
    for name, value in _iter_module_values(module):
        if has_declaration(value, kind="task"):
            continue
        if not isinstance(value, Task):
            continue
        validate_task(value)
        if id(value) in object_seen:
            continue
        fallback_found = True
        if value.task_id in id_sources:
            raise SnowlValidationError(
                f"Duplicate task_id '{value.task_id}' discovered between {id_sources[value.task_id]} "
                f"and fallback object '{name}'. Add @task(...) or rename id."
            )
        tasks.append(value)
        object_seen.add(id(value))
        id_sources[value.task_id] = f"fallback object '{name}'"

    if strict_ids and fallback_found:
        raise SnowlValidationError(
            "SNOWL_DISCOVERY_STRICT_IDS=1 requires decorator-based declarations. "
            "Fallback task objects were found; mark them with @task(...)."
        )
    return tasks


def _discover_agents(module: ModuleType) -> list[Agent]:
    strict_ids = _discovery_strict_ids_enabled()
    agents: list[Agent] = []
    fallback_found = False
    seen_identity: dict[tuple[str, str], tuple[int, str]] = {}

    def _to_agent_variants(
        item: Any,
        *,
        source: str,
        declared_agent_id: str | None = None,
    ) -> list[Agent]:
        if isinstance(item, (list, tuple, set)):
            out: list[Agent] = []
            for child in item:
                out.extend(
                    _to_agent_variants(
                        child, source=source, declared_agent_id=declared_agent_id
                    )
                )
            return out

        if isinstance(item, AgentVariant):
            variant = item
            if declared_agent_id and variant.agent_id != declared_agent_id:
                variant = AgentVariant(
                    agent=variant.agent,
                    agent_id=declared_agent_id,
                    variant_id=variant.variant_id,
                    model=variant.model,
                    params=dict(variant.params),
                    provenance=dict(variant.provenance),
                )
            validate_agent_variant(variant)
            return [bind_agent_variant(variant)]

        if (
            isinstance(item, dict)
            and "agent" in item
            and "agent_id" in item
            and "variant_id" in item
        ):
            variant = AgentVariant(
                agent=item["agent"],
                agent_id=declared_agent_id or str(item["agent_id"]),
                variant_id=str(item["variant_id"]),
                model=(str(item["model"]) if item.get("model") is not None else None),
                params=dict(item.get("params") or {}),
                provenance=dict(item.get("provenance") or {}),
            )
            validate_agent_variant(variant)
            return [bind_agent_variant(variant)]

        run_fn = getattr(item, "run", None)
        if run_fn is None or not callable(run_fn):
            raise SnowlValidationError(
                f"Agent declaration source {source} did not resolve to an agent-like object."
            )
        validate_agent(item)
        variant = AgentVariant(
            agent=item,
            agent_id=declared_agent_id or str(getattr(item, "agent_id")),
            variant_id=str(getattr(item, "variant_id", "default")),
            model=(str(getattr(item, "model")) if getattr(item, "model", None) is not None else None),
            params={},
            provenance={},
        )
        validate_agent_variant(variant)
        return [bind_agent_variant(variant)]

    def _append_discovered(discovered: list[Agent], source: str) -> None:
        for bound in discovered:
            key = (
                str(getattr(bound, "agent_id", "")),
                str(getattr(bound, "variant_id", "default")),
            )
            ref = (id(getattr(bound, "agent", bound)), source)
            existing = seen_identity.get(key)
            if existing is not None:
                if existing[0] == ref[0]:
                    continue
                raise SnowlValidationError(
                    f"Duplicate AgentVariant identity found for agent_id='{key[0]}' and variant_id='{key[1]}' "
                    f"between {existing[1]} and {source}."
                )
            seen_identity[key] = ref
            agents.append(bound)

    for name, value, decl in _iter_decorated_values(module, "agent"):
        declared_id = decl.object_id
        for resolved in _resolve_declared_candidate(value, "agent"):
            discovered = _to_agent_variants(
                resolved,
                source=f"decorated declaration '{name}'",
                declared_agent_id=declared_id,
            )
            _append_discovered(discovered, f"decorated declaration '{name}'")

    for name, value in _iter_module_values(module):
        if has_declaration(value, kind="agent"):
            continue
        if inspect.isclass(value):
            continue
        try:
            discovered = _to_agent_variants(value, source=f"fallback object '{name}'")
        except SnowlValidationError:
            continue
        fallback_found = True
        _append_discovered(discovered, f"fallback object '{name}'")

    # Deterministic order for stable plans and artifacts.
    agents = sorted(
        agents,
        key=lambda a: (
            str(getattr(a, "agent_id", "")),
            str(getattr(a, "variant_id", "default")),
        ),
    )
    if strict_ids and fallback_found:
        raise SnowlValidationError(
            "SNOWL_DISCOVERY_STRICT_IDS=1 requires decorator-based declarations. "
            "Fallback agent objects were found; mark them with @agent(...)."
        )
    return agents


def _discover_scorers(module: ModuleType) -> list[Scorer]:
    strict_ids = _discovery_strict_ids_enabled()
    scorers: list[Scorer] = []
    fallback_found = False
    object_seen: set[int] = set()
    id_sources: dict[str, str] = {}

    def _normalize_scorer(item: Any, source: str, declared_id: str | None = None) -> list[Scorer]:
        if isinstance(item, (list, tuple, set)):
            out: list[Scorer] = []
            for child in item:
                out.extend(_normalize_scorer(child, source=source, declared_id=declared_id))
            return out
        score_fn = getattr(item, "score", None)
        if score_fn is None or not callable(score_fn):
            raise SnowlValidationError(f"Scorer declaration source {source} is not scorer-like.")
        if declared_id is not None:
            try:
                setattr(item, "scorer_id", declared_id)
            except Exception:
                pass
        validate_scorer(item)
        return [item]

    for name, value, decl in _iter_decorated_values(module, "scorer"):
        for resolved in _resolve_declared_candidate(value, "scorer"):
            for item in _normalize_scorer(
                resolved,
                source=f"decorated declaration '{name}'",
                declared_id=decl.object_id,
            ):
                if id(item) in object_seen:
                    continue
                scorer_id = str(getattr(item, "scorer_id"))
                if scorer_id in id_sources:
                    raise SnowlValidationError(
                        f"Duplicate scorer_id '{scorer_id}' discovered between {id_sources[scorer_id]} "
                        f"and decorated declaration '{name}'."
                    )
                object_seen.add(id(item))
                id_sources[scorer_id] = f"decorated declaration '{name}'"
                scorers.append(item)

    for name, value in _iter_module_values(module):
        if has_declaration(value, kind="scorer"):
            continue
        if inspect.isclass(value):
            continue
        try:
            normalized = _normalize_scorer(value, source=f"fallback object '{name}'")
        except SnowlValidationError:
            continue
        fallback_found = True
        for item in normalized:
            if id(item) in object_seen:
                continue
            scorer_id = str(getattr(item, "scorer_id"))
            if scorer_id in id_sources:
                raise SnowlValidationError(
                    f"Duplicate scorer_id '{scorer_id}' discovered between {id_sources[scorer_id]} "
                    f"and fallback object '{name}'. Add @scorer(...) or rename id."
                )
            object_seen.add(id(item))
            id_sources[scorer_id] = f"fallback object '{name}'"
            scorers.append(item)

    if strict_ids and fallback_found:
        raise SnowlValidationError(
            "SNOWL_DISCOVERY_STRICT_IDS=1 requires decorator-based declarations. "
            "Fallback scorer objects were found; mark them with @scorer(...)."
        )
    return scorers


def _discover_tools(module: ModuleType) -> list[Any]:
    registry = get_default_tool_registry()
    discovered: list[Any] = []

    for _, value in vars(module).items():
        if isinstance(value, ToolSpec):
            registry.register(value)
            discovered.append(value)
        elif hasattr(value, "__snowl_tool_spec__"):
            spec = resolve_tool_spec(value)
            registry.register(spec)
            discovered.append(value)

    return discovered


TItem = TypeVar("TItem")


def _select_by_id(items: list[TItem], ids: list[str] | None, id_getter) -> list[TItem]:
    if not ids:
        return items
    id_set = {x.strip() for x in ids if x.strip()}
    selected = [item for item in items if id_getter(item) in id_set]
    return selected


def _build_plan(tasks: list[Task], agents: list[Agent]) -> EvalPlan:
    task_ids = [t.task_id for t in tasks]
    agent_ids = sorted({getattr(a, "agent_id") for a in agents})
    variant_ids = sorted({str(getattr(a, "variant_id", "default")) for a in agents})

    sample_buckets: list[tuple[Task, list[dict[str, Any]]]] = []
    sample_count = 0
    for task in tasks:
        samples = [dict(sample) for sample in task.iter_samples()]
        sample_count += len(samples)
        sample_buckets.append((task, samples))

    trials: list[PlanTrial] = []
    for task, samples in sample_buckets:
        for sample in samples:
            sample_id = str(sample.get("id")) if sample.get("id") is not None else None
            for agent in agents:
                trials.append(
                    PlanTrial(
                        task=task,
                        agent=agent,
                        sample=sample,
                        task_id=task.task_id,
                        agent_id=getattr(agent, "agent_id"),
                        variant_id=str(getattr(agent, "variant_id", "default")),
                        model=(
                            str(getattr(agent, "model"))
                            if getattr(agent, "model", None) is not None
                            else None
                        ),
                        sample_id=sample_id,
                    )
                )

    if len(task_ids) == 1 and len(agent_ids) == 1 and len(variant_ids) == 1:
        mode = "single"
    elif len(task_ids) > 1 and len(agent_ids) == 1 and len(variant_ids) == 1:
        mode = "task_sweep"
    elif len(task_ids) == 1 and (len(agent_ids) > 1 or len(variant_ids) > 1):
        mode = "agent_compare"
    else:
        mode = "matrix"

    return EvalPlan(
        mode=mode,
        task_ids=task_ids,
        agent_ids=agent_ids,
        variant_ids=variant_ids,
        sample_count=sample_count,
        trials=trials,
    )


def _trial_key(trial: PlanTrial) -> str:
    if trial.sample_id is not None:
        sample_token = trial.sample_id
    else:
        sample_json = json.dumps(trial.sample, ensure_ascii=False, sort_keys=True)
        sample_token = hashlib.sha1(sample_json.encode("utf-8")).hexdigest()[:12]
    return f"{trial.task_id}::{trial.agent_id}::{trial.variant_id}::{sample_token}"


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
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
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


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _trial_models(plan: EvalPlan) -> dict[str, str | None]:
    return {_trial_key(trial): trial.model for trial in plan.trials}


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


def _write_live_run_metadata(
    *,
    out_dir: Path,
    run_id: str,
    experiment_id: str,
    benchmark: str,
    plan: EvalPlan,
    task_monitor: TaskMonitor,
    controls: dict[str, Any],
    trial_count: int,
    event_stream_mode: str,
) -> None:
    model_by_trial_key = _trial_models(plan)
    _write_json_file(
        out_dir / "plan.json",
        {
            "mode": plan.mode,
            "task_ids": plan.task_ids,
            "agent_ids": plan.agent_ids,
            "variant_ids": plan.variant_ids,
            "sample_count": plan.sample_count,
            "trial_count": trial_count,
        },
    )
    _write_json_file(
        out_dir / "manifest.json",
        {
            "schema_version": RESULT_SCHEMA_VERSION,
            "result_schema_uri": RESULT_SCHEMA_URI,
            "aggregate_schema_uri": AGGREGATE_SCHEMA_URI,
            "run_id": run_id,
            "experiment_id": experiment_id,
            "benchmark": benchmark,
            "event_stream_mode": event_stream_mode,
            "status": "running",
            "research_exports": {
                "events_jsonl": "events.jsonl",
            },
        },
    )
    _write_json_file(
        out_dir / "profiling.json",
        {
            "run": {
                "run_id": run_id,
                "experiment_id": experiment_id,
                "benchmark": benchmark,
            },
            "controls": controls,
            "throughput": {
                "trial_count": trial_count,
            },
            "task_monitor": _task_monitor_rows(task_monitor, model_by_trial_key=model_by_trial_key),
        },
    )


def _to_serializable_outcome(outcome: TrialOutcome) -> dict[str, Any]:
    scores = {
        k: {
            "value": v.value,
            "explanation": v.explanation,
            "metadata": dict(v.metadata),
        }
        for k, v in outcome.scores.items()
    }
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "schema_uri": RESULT_SCHEMA_URI,
        "task_result": outcome.task_result.to_dict(),
        "scores": scores,
        "trace": outcome.trace,
    }


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


def _benchmark_name_for_task(task: Task) -> str:
    metadata = getattr(task, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        return "custom"
    value = str(metadata.get("benchmark") or metadata.get("benchmark_name") or "").strip().lower()
    return value or "custom"


class _LiveEventsWriter:
    """Append-only live events writer with stable event ids."""

    def __init__(self, *, path: Path, run_id: str) -> None:
        self._path = path
        self._run_id = run_id
        self._lock = threading.Lock()
        self._event_index = 0
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._path.open("a", encoding="utf-8")

    def append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._event_index += 1
            idx = self._event_index
            event_id = str(row.get("event_id") or f"{self._run_id}:{idx}")
            event_row = {
                "schema_version": RESULT_SCHEMA_VERSION,
                "run_id": self._run_id,
                "event_index": idx,
                "seq": idx,
                "event_id": event_id,
                **dict(row),
            }
            event_row["event_index"] = idx
            event_row["seq"] = idx
            event_row["event_id"] = event_id
            event_row["run_id"] = self._run_id
            self._fh.write(json.dumps(event_row, ensure_ascii=False) + "\n")
            self._fh.flush()
            return event_row

    def close(self) -> None:
        with self._lock:
            try:
                self._fh.close()
            except Exception:
                pass


def _write_artifacts(
    *,
    base_dir: Path,
    run_id: str,
    outcomes: list[TrialOutcome],
    plan: EvalPlan,
    summary: EvalSummary,
    rerun_command: str,
    out_dir: Path | None = None,
    run_log_lines: list[str] | None = None,
    event_rows: list[dict[str, Any]] | None = None,
    profiling: dict[str, Any] | None = None,
    experiment_id: str | None = None,
    event_stream_mode: str = "batch_write",
) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if out_dir is None:
        out_dir = _prepare_run_artifacts_dir(base_dir=base_dir, run_id=run_id)

    (out_dir / "plan.json").write_text(
        json.dumps(
            {
                "mode": plan.mode,
                "task_ids": plan.task_ids,
                "agent_ids": plan.agent_ids,
                "variant_ids": plan.variant_ids,
                "sample_count": plan.sample_count,
                "trial_count": len(plan.trials),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (out_dir / "summary.json").write_text(
        json.dumps(summary.__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    aggregate = aggregate_outcomes(outcomes)
    (out_dir / "aggregate.json").write_text(
        json.dumps(
            {
                "schema_uri": AGGREGATE_SCHEMA_URI,
                "schema_version": RESULT_SCHEMA_VERSION,
                "by_task_agent": aggregate.by_task_agent,
                "matrix": aggregate.matrix,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (out_dir / "outcomes.json").write_text(
        json.dumps([_to_serializable_outcome(o) for o in outcomes], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Research-friendly exports
    trials_jsonl_path = out_dir / "trials.jsonl"
    with trials_jsonl_path.open("w", encoding="utf-8") as f:
        for idx, outcome in enumerate(outcomes, start=1):
            row = _to_serializable_outcome(outcome)
            row["run_id"] = run_id
            row["schema_version"] = RESULT_SCHEMA_VERSION
            row["trial_index"] = idx
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    events_jsonl_path = out_dir / "events.jsonl"
    with events_jsonl_path.open("w", encoding="utf-8") as f:
        for idx, row in enumerate(event_rows or [], start=1):
            row_dict = dict(row)
            event_index = int(row_dict.get("event_index") or idx)
            event_id = str(row_dict.get("event_id") or f"{run_id}:{event_index}")
            event_row = {
                "schema_version": RESULT_SCHEMA_VERSION,
                "run_id": run_id,
                "event_index": event_index,
                "seq": event_index,
                "event_id": event_id,
                **row_dict,
            }
            event_row["run_id"] = run_id
            event_row["event_index"] = event_index
            event_row["seq"] = event_index
            event_row["event_id"] = event_id
            f.write(json.dumps(event_row, ensure_ascii=False) + "\n")

    metrics_wide_path = out_dir / "metrics_wide.csv"
    metric_names = sorted(
        {
            str(metric_name)
            for outcome in outcomes
            for metric_name in (outcome.scores or {}).keys()
        }
    )
    fieldnames = [
        "schema_version",
        "run_id",
        "task_id",
        "agent_id",
        "variant_id",
        "sample_id",
        "status",
    ] + metric_names
    with metrics_wide_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for outcome in outcomes:
            tr = outcome.task_result
            row: dict[str, Any] = {
                "schema_version": RESULT_SCHEMA_VERSION,
                "run_id": run_id,
                "task_id": tr.task_id,
                "agent_id": tr.agent_id,
                "variant_id": str((tr.payload or {}).get("variant_id") or "default"),
                "sample_id": tr.sample_id,
                "status": tr.status.value,
            }
            for metric_name in metric_names:
                score = (outcome.scores or {}).get(metric_name)
                row[metric_name] = (float(score.value) if score is not None else "")
            writer.writerow(row)

    diagnostics_dir = out_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_index: list[dict[str, Any]] = []
    for idx, outcome in enumerate(outcomes, start=1):
        sandbox = outcome.trace.get("sandbox") if isinstance(outcome.trace, dict) else None
        tr = outcome.task_result
        if not sandbox and tr.status.value not in {"error", "limit_exceeded", "cancelled"}:
            continue
        sample = tr.sample_id if tr.sample_id is not None else str(idx)
        variant_id = str((tr.payload or {}).get("variant_id") or "default")
        diag_name = f"{tr.task_id}__{tr.agent_id}__{variant_id}__{sample}.json"
        diag_file = diagnostics_dir / diag_name
        payload = {
            "task_id": tr.task_id,
            "agent_id": tr.agent_id,
            "variant_id": variant_id,
            "sample_id": tr.sample_id,
            "status": tr.status.value,
            "sandbox": sandbox,
            "error": tr.error.__dict__ if tr.error else None,
        }
        diag_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        diagnostics_index.append(
            {
                "task_id": tr.task_id,
                "agent_id": tr.agent_id,
                "variant_id": variant_id,
                "sample_id": tr.sample_id,
                "status": tr.status.value,
                "path": f"diagnostics/{diag_name}",
            }
        )

    (out_dir / "diagnostics_index.json").write_text(
        json.dumps(diagnostics_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": RESULT_SCHEMA_VERSION,
                "result_schema_uri": RESULT_SCHEMA_URI,
                "aggregate_schema_uri": AGGREGATE_SCHEMA_URI,
                "run_id": run_id,
                "experiment_id": experiment_id,
                "benchmark": profiling.get("run", {}).get("benchmark") if isinstance(profiling, dict) else None,
                "created_at_utc": now,
                "rerun_command": rerun_command,
                "diagnostics_count": len(diagnostics_index),
                "event_stream_mode": event_stream_mode,
                "research_exports": {
                    "trials_jsonl": "trials.jsonl",
                    "events_jsonl": "events.jsonl",
                    "metrics_wide_csv": "metrics_wide.csv",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Basic HTML report (summary + comparison + failures).
    failure_rows = []
    for item in diagnostics_index:
        if item["status"] in {"error", "limit_exceeded", "cancelled"}:
            failure_rows.append(
                f"<tr><td>{item['task_id']}</td><td>{item['agent_id']}</td><td>{item['sample_id']}</td><td>{item['status']}</td><td><a href='{item['path']}'>diagnostic</a></td></tr>"
            )
    matrix_rows = []
    for task_id in sorted(aggregate.matrix.keys()):
        agents = aggregate.matrix[task_id]
        for agent_id in sorted(agents.keys()):
            metrics = agents[agent_id]
            metric_text = ", ".join([f"{k}: {v:.3f}" for k, v in sorted(metrics.items())])
            matrix_rows.append(
                f"<tr><td>{task_id}</td><td>{agent_id}</td><td>{metric_text}</td></tr>"
            )
    html = f"""<!doctype html>\n<html><head><meta charset='utf-8'/><title>Snowl Report</title>\n<style>body{{font-family:Menlo,Consolas,monospace;padding:20px}} table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #ddd;padding:6px}} .cards{{display:grid;grid-template-columns:repeat(3,minmax(120px,1fr));gap:8px}} .card{{border:1px solid #ccc;padding:8px}}</style>\n</head><body>\n<h1>Snowl Report</h1>\n<div class='cards'>\n<div class='card'>Total: {summary.total}</div>\n<div class='card'>Success: {summary.success}</div>\n<div class='card'>Incorrect: {summary.incorrect}</div>\n<div class='card'>Error: {summary.error}</div>\n<div class='card'>Limit: {summary.limit_exceeded}</div>\n<div class='card'>Cancelled: {summary.cancelled}</div>\n</div>\n<h2>Comparison</h2>\n<table><thead><tr><th>Task</th><th>Agent</th><th>Metrics</th></tr></thead><tbody>{''.join(matrix_rows) or '<tr><td colspan=3>no data</td></tr>'}</tbody></table>\n<h2>Failures</h2>\n<table><thead><tr><th>Task</th><th>Agent</th><th>Sample</th><th>Status</th><th>Diagnostic</th></tr></thead><tbody>{''.join(failure_rows) or '<tr><td colspan=5>no failures</td></tr>'}</tbody></table>\n</body></html>"""
    (out_dir / "report.html").write_text(html, encoding="utf-8")

    if run_log_lines is not None:
        (out_dir / "run.log").write_text(
            "\n".join(run_log_lines or []) + ("\n" if run_log_lines else ""),
            encoding="utf-8",
        )
    (out_dir / "profiling.json").write_text(
        json.dumps(profiling or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return out_dir


def _build_rerun_command(
    entry_path: Path,
    task_filter: list[str] | None,
    agent_filter: list[str] | None,
    variant_filter: list[str] | None = None,
    experiment_id: str | None = None,
) -> str:
    cmd = ["snowl", "eval", str(entry_path)]
    if task_filter:
        cmd.extend(["--task", ",".join(task_filter)])
    if agent_filter:
        cmd.extend(["--agent", ",".join(agent_filter)])
    if variant_filter:
        cmd.extend(["--variant", ",".join(variant_filter)])
    if experiment_id:
        cmd.extend(["--experiment-id", str(experiment_id)])
    return " ".join(cmd)


def _is_docker_like_task(task: Task) -> bool:
    try:
        env_type = str(getattr(task.env_spec, "env_type", "") or "").lower()
    except Exception:
        env_type = ""
    if env_type in {"terminal", "gui", "docker"}:
        return True
    try:
        sandbox_spec = getattr(task.env_spec, "sandbox_spec", None)
        if sandbox_spec is not None:
            provider = str(getattr(sandbox_spec, "provider", "") or "").lower()
            if provider in {"docker", "podman"}:
                return True
    except Exception:
        pass
    metadata = getattr(task, "metadata", {}) or {}
    if isinstance(metadata, dict):
        bench = str(metadata.get("benchmark") or metadata.get("benchmark_name") or "").lower()
        if bench in {"terminalbench", "osworld"}:
            return True
    return False


def _pick_event_value(event: dict[str, Any], key: str) -> Any:
    if key in event and event.get(key) is not None:
        return event.get(key)
    payload = event.get("payload")
    if isinstance(payload, dict):
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
        nested = payload.get("payload")
        if isinstance(nested, dict):
            return nested.get(key)
    return None


def _enrich_event_row(
    raw_event: dict[str, Any],
    *,
    run_id: str,
    experiment_id: str,
    trial: PlanTrial | None,
    benchmark_hint: str | None,
) -> dict[str, Any]:
    row = dict(raw_event)
    task_id = str(
        row.get("task_id")
        or (trial.task_id if trial is not None else "")
        or _pick_event_value(row, "task_id")
        or ""
    ).strip()
    agent_id = str(
        row.get("agent_id")
        or (trial.agent_id if trial is not None else "")
        or _pick_event_value(row, "agent_id")
        or ""
    ).strip()
    variant_id = str(
        row.get("variant_id")
        or (trial.variant_id if trial is not None else "default")
        or _pick_event_value(row, "variant_id")
        or "default"
    ).strip() or "default"
    sample_id_raw = (
        row.get("sample_id")
        or (trial.sample_id if trial is not None else None)
        or _pick_event_value(row, "sample_id")
    )
    sample_id = (str(sample_id_raw).strip() if sample_id_raw is not None else "")
    model = str(
        row.get("model")
        or (trial.model if trial is not None else "")
        or _pick_event_value(row, "model")
        or ""
    ).strip()
    benchmark = str(
        row.get("benchmark")
        or (trial.task.metadata.get("benchmark") if trial is not None and isinstance(trial.task.metadata, dict) else "")
        or _pick_event_value(row, "benchmark")
        or benchmark_hint
        or "custom"
    ).strip().lower() or "custom"
    ts_raw = row.get("ts_ms")
    ts_ms = int(ts_raw) if isinstance(ts_raw, (int, float)) else int(datetime.now(timezone.utc).timestamp() * 1000)

    trial_key = row.get("trial_key")
    if not isinstance(trial_key, str) or not trial_key.strip():
        if trial is not None:
            trial_key = _trial_key(trial)
        elif task_id and agent_id:
            sample_token = sample_id or "-"
            trial_key = f"{task_id}::{agent_id}::{variant_id}::{sample_token}"
        else:
            trial_key = ""

    row.update(
        {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "trial_key": trial_key,
            "benchmark": benchmark,
            "task_id": task_id or None,
            "agent_id": agent_id or None,
            "variant_id": variant_id,
            "model": model or None,
            "sample_id": sample_id or None,
            "ts_ms": ts_ms,
        }
    )
    return row


def _derive_pretask_events(event: dict[str, Any]) -> list[dict[str, Any]]:
    name = str(event.get("event", "")).strip()
    if not name or name.startswith("pretask."):
        return []

    exit_code = _pick_event_value(event, "exit_code")
    command_text = str(_pick_event_value(event, "command_text") or "")
    command_text_l = command_text.lower()
    ready = _pick_event_value(event, "ready")
    code = str(_pick_event_value(event, "code") or "")

    def _status_from_exit(default_running: str = "running") -> str:
        if isinstance(exit_code, int):
            return "success" if exit_code == 0 else "failed"
        return default_running

    def _mk(stage_event: str, *, status: str, source: str) -> dict[str, Any]:
        out = {
            "event": stage_event,
            "phase": "env",
            "status": status,
            "message": status,
            "source_event": source,
        }
        for key in (
            "task_id",
            "agent_id",
            "variant_id",
            "sample_id",
            "trial_key",
            "model",
            "benchmark",
            "project",
            "compose_file",
            "command_text",
            "exit_code",
            "duration_ms",
            "ts_ms",
            "run_id",
            "experiment_id",
        ):
            value = _pick_event_value(event, key)
            if value is not None:
                out[key] = value
        return out

    out: list[dict[str, Any]] = []

    if name.startswith("runtime.env.preflight."):
        status = "failed" if name.endswith(".error") else ("success" if name.endswith(".finish") or name.endswith(".hit") else "running")
        out.append(_mk("pretask.preflight", status=status, source=name))
        return out

    if "container.build" in name:
        out.append(_mk("pretask.build", status=_status_from_exit(), source=name))
        return out

    if name in {"runtime.env.command.start", "runtime.env.command.finish", "runtime.env.command.timeout"}:
        is_build = (" compose " in command_text_l and " build" in command_text_l) or command_text_l.startswith("docker compose") and " build" in command_text_l
        is_start = (
            (" compose " in command_text_l and " up" in command_text_l)
            or command_text_l.startswith("docker run")
            or (" compose " in command_text_l and " exec" in command_text_l and "tmux" in command_text_l)
        )
        if is_build:
            status = "running" if name.endswith(".start") else ("timeout" if name.endswith(".timeout") else _status_from_exit())
            out.append(_mk("pretask.build", status=status, source=name))
        if is_start:
            status = "running" if name.endswith(".start") else ("timeout" if name.endswith(".timeout") else _status_from_exit())
            out.append(_mk("pretask.start", status=status, source=name))
        return out

    if "container.starting" in name:
        out.append(_mk("pretask.start", status="running", source=name))
        return out

    if "container.started" in name:
        if isinstance(exit_code, int) and exit_code != 0:
            status = "failed"
        elif ready is False:
            status = "failed"
        else:
            status = "success"
        out.append(_mk("pretask.start", status=status, source=name))
        return out

    if "visual_probe" in name or name == "gui.container.wait":
        out.append(_mk("pretask.ready_probe", status="running", source=name))
        return out

    if "visual_ready" in name or name == "gui.container.ready":
        out.append(_mk("pretask.ready", status="success", source=name))
        return out

    if name == "runtime.trial.error" and code == "container_runtime_error":
        out.append(_mk("pretask.failed", status="failed", source=name))
        return out

    if "container.retry" in name:
        out.append(_mk("pretask.start", status="retry", source=name))
        return out

    return out


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


def load_project_components(
    path: str | Path,
    *,
    require_task_file: bool = True,
) -> ProjectComponents:
    base_dir, _config, code = _resolve_project_entry(path)

    task_file = code.task_module if code is not None else (base_dir / "task.py")
    agent_file = code.agent_module if code is not None else (base_dir / "agent.py")
    scorer_file = code.scorer_module if code is not None else (base_dir / "scorer.py")
    tool_file = code.tool_module if code is not None else (base_dir / "tool.py")

    required = [agent_file, scorer_file]
    if require_task_file:
        required.insert(0, task_file)

    missing = [p.name for p in required if not p.exists()]
    if missing:
        raise SnowlValidationError(
            f"Missing required eval files in {base_dir}: {', '.join(missing)}"
        )

    tool_registry = get_default_tool_registry()
    tool_registry.clear()
    if tool_file is not None and tool_file.exists():
        tool_module = _load_module("snowl_user_tool", tool_file)
        _discover_tools(tool_module)

    tasks: list[Task] = []
    if require_task_file:
        task_module = _load_module("snowl_user_task", task_file)
        tasks = _discover_tasks(task_module)

    agent_module = _load_module("snowl_user_agent", agent_file)
    scorer_module = _load_module("snowl_user_scorer", scorer_file)
    agents = _discover_agents(agent_module)
    scorers = _discover_scorers(scorer_module)

    if require_task_file and not tasks:
        raise SnowlValidationError("No Task instances discovered in task.py")
    if not agents:
        raise SnowlValidationError("No Agent instances discovered in agent.py")
    if not scorers:
        raise SnowlValidationError("No Scorer instances discovered in scorer.py")

    return ProjectComponents(
        tasks=tasks,
        agents=agents,
        scorers=scorers,
        tool_specs=tool_registry.list(),
    )


def _available_memory_gb() -> float | None:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        return float(page_size * avail_pages) / (1024.0**3)
    except Exception:
        return None


def _auto_container_slots(*, benchmark: str, cpu_count: int | None = None, mem_gb: float | None = None) -> int:
    cpu = max(1, int(cpu_count or os.cpu_count() or 1))
    memory = mem_gb if mem_gb is not None else _available_memory_gb()
    benchmark_key = str(benchmark or "").strip().lower()
    if benchmark_key in {"", "custom", "strongreject", "toolemu", "agentsafetybench"}:
        return 0
    if benchmark_key == "terminalbench":
        by_cpu = max(1, min(4, cpu // 2))
        if memory is None:
            return by_cpu
        return max(1, min(by_cpu, int(memory // 6) or 1))
    if benchmark_key == "osworld":
        by_cpu = max(1, min(2, cpu // 4 or 1))
        if memory is None:
            return by_cpu
        return max(1, min(by_cpu, int(memory // 10) or 1))
    return max(1, min(2, cpu // 2 or 1))


def _resolve_runtime_budgets(
    *,
    tasks: list[Task],
    project_config: ProjectConfig | None,
    interaction_controller: Any | None,
    max_running_trials: int | None,
    max_container_slots: int | None,
    max_builds: int | None,
    max_scoring_tasks: int | None,
    provider_budgets: dict[str, int] | None,
) -> dict[str, Any]:
    runtime_cfg = project_config.runtime if project_config is not None else None
    explicit_running = max_running_trials is not None
    benchmark_names = sorted({_benchmark_name_for_task(task) for task in tasks})
    benchmark_hint = benchmark_names[0] if len(benchmark_names) == 1 else "mixed"

    if max_running_trials is None:
        max_running_trials = runtime_cfg.max_running_trials if runtime_cfg is not None else None
    if max_builds is None:
        max_builds = runtime_cfg.max_builds if runtime_cfg is not None else None
    if max_scoring_tasks is None:
        max_scoring_tasks = runtime_cfg.max_scoring_tasks if runtime_cfg is not None else None
    if provider_budgets is None:
        provider_budgets = dict(runtime_cfg.provider_budgets) if runtime_cfg is not None else {}

    auto_container = False
    if max_container_slots is None:
        raw = runtime_cfg.max_container_slots if runtime_cfg is not None else "auto"
        if isinstance(raw, str) and raw.strip().lower() == "auto":
            auto_container = True
            max_container_slots = _auto_container_slots(benchmark=benchmark_hint)
        elif raw is None:
            auto_container = True
            max_container_slots = _auto_container_slots(benchmark=benchmark_hint)
        else:
            max_container_slots = int(raw)

    if max_running_trials is None:
        max_running_trials = min(8, max(1, int(os.cpu_count() or 4)))
    if max_builds is None:
        max_builds = 2
    if max_scoring_tasks is None:
        max_scoring_tasks = max_running_trials

    if interaction_controller is not None:
        max_running_trials = 1
    docker_like = any(_is_docker_like_task(t) for t in tasks)
    if docker_like and not explicit_running:
        max_running_trials = 1

    if project_config is not None and project_config.provider.id not in provider_budgets:
        provider_budgets[project_config.provider.id] = max(max_running_trials, max_scoring_tasks)
    if not provider_budgets:
        provider_budgets["default"] = max(max_running_trials, max_scoring_tasks)

    return {
        "max_running_trials": max_running_trials,
        "max_container_slots": max_container_slots,
        "max_builds": max_builds,
        "max_scoring_tasks": max_scoring_tasks,
        "provider_budgets": provider_budgets,
        "auto_container_slots": max_container_slots if auto_container else None,
        "docker_like": docker_like,
    }


async def run_eval_with_components(
    *,
    entry_path: Path,
    base_dir: Path,
    tasks: list[Task],
    agents: list[Agent],
    scorer: Scorer,
    tool_specs: list[ToolSpec],
    task_filter: list[str] | None = None,
    agent_filter: list[str] | None = None,
    variant_filter: list[str] | None = None,
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
    max_trials: int | None = None,
    max_sandboxes: int | None = None,
    max_model_calls: int | None = None,
    project_config: ProjectConfig | None = None,
    experiment_id: str | None = None,
    on_run_bootstrap: Callable[[EvalRunBootstrap], None] | None = None,
) -> EvalRunResult:
    tasks = _select_by_id(tasks, task_filter, lambda t: t.task_id)
    agents = _select_by_id(agents, agent_filter, lambda a: getattr(a, "agent_id"))
    agents = _select_by_id(agents, variant_filter, lambda a: str(getattr(a, "variant_id", "default")))

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

    budgets = _resolve_runtime_budgets(
        tasks=tasks,
        project_config=project_config,
        interaction_controller=interaction_controller,
        max_running_trials=max_running_trials,
        max_container_slots=max_container_slots,
        max_builds=max_builds,
        max_scoring_tasks=max_scoring_tasks,
        provider_budgets=provider_budgets,
    )
    docker_like = bool(budgets["docker_like"])
    scheduler = ResourceScheduler(
        max_running_trials=budgets["max_running_trials"],
        max_container_slots=budgets["max_container_slots"],
        max_builds=budgets["max_builds"],
        max_scoring_tasks=budgets["max_scoring_tasks"],
        provider_budgets=budgets["provider_budgets"],
    )
    set_compose_build_slot_factory(scheduler.build_slot)
    OpenAICompatibleChatClient.set_global_model_call_slot_resolver(
        lambda config: scheduler.provider_slot(getattr(config, "provider_id", "default"))
    )

    run_started = int(datetime.now(timezone.utc).timestamp() * 1000)
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    if not experiment_id:
        experiment_id = _default_experiment_id(base_dir=base_dir, started_ms=run_started)
    artifacts_dir_live = _prepare_run_artifacts_dir(base_dir=base_dir, run_id=run_id)
    live_run_log_path = artifacts_dir_live / "run.log"
    live_run_log_path.touch(exist_ok=True)
    live_events_path = artifacts_dir_live / "events.jsonl"
    event_writer = _LiveEventsWriter(path=live_events_path, run_id=run_id)
    plan = _build_plan(tasks, agents)
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
        if resume
        else {"completed": {}, "in_progress": {}, "failed_keys": [], "meta": {}}
    )
    checkpoint.setdefault("completed", {})
    checkpoint.setdefault("in_progress", {})
    checkpoint.setdefault("failed_keys", [])
    checkpoint.setdefault("meta", {})

    failed_only_keys: set[str] = set()
    if rerun_failed_only:
        failed_only_keys = _failed_trial_keys_from_latest_run(base_dir)
        if not failed_only_keys:
            raise SnowlValidationError("No failed trials found in latest run for rerun-failed-only.")

    outcomes: list[TrialOutcome] = []
    run_log_lines: list[str] = []
    event_rows: list[dict[str, Any]] = []
    task_monitor = TaskMonitor()
    benchmark_names = sorted({_benchmark_name_for_task(task) for task in tasks})
    benchmark_hint = benchmark_names[0] if len(benchmark_names) == 1 else "mixed"

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
        enriched = _enrich_event_row(
            row,
            run_id=run_id,
            experiment_id=str(experiment_id),
            trial=trial,
            benchmark_hint=benchmark_hint,
        )
        persisted = event_writer.append(enriched)
        event_rows.append(dict(persisted))
        if trial is not None:
            for synthetic in _derive_pretask_events(persisted):
                synthetic_enriched = _enrich_event_row(
                    synthetic,
                    run_id=run_id,
                    experiment_id=str(experiment_id),
                    trial=trial,
                    benchmark_hint=benchmark_hint,
                )
                persisted_synth = event_writer.append(synthetic_enriched)
                event_rows.append(dict(persisted_synth))
        return persisted

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
    for raw in completed.values():
        # restore checkpointed outcomes for summary/compare continuity
        tr_data = raw["task_result"]
        scores_data = raw.get("scores", {})
        from snowl.core import Score, TaskResult  # local to avoid import cycle
        task_result = TaskResult.from_dict(tr_data)
        scores = {k: Score(value=v["value"], explanation=v.get("explanation"), metadata=v.get("metadata", {})) for k, v in scores_data.items()}
        outcomes.append(TrialOutcome(task_result=task_result, scores=scores, trace=raw.get("trace", {})))

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
        key = _trial_key(trial)
        if rerun_failed_only and key not in failed_only_keys:
            continue
        if resume and key in completed:
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

    total = len(executable_trials) + len(outcomes)
    _write_live_run_metadata(
        out_dir=artifacts_dir_live,
        run_id=run_id,
        experiment_id=str(experiment_id),
        benchmark=benchmark_hint,
        plan=plan,
        task_monitor=task_monitor,
        controls=scheduler.controls(),
        trial_count=total,
        event_stream_mode="live_append",
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
    if resume:
        _save_checkpoint(base_dir, checkpoint_key, checkpoint)

    has_sandbox_tasks = any(getattr(t.env_spec, "sandbox_spec", None) is not None for t in tasks)
    shared_sandbox_runtime = (
        scheduler.wrap_sandbox_runtime(WarmPoolSandboxRuntime())
        if has_sandbox_tasks
        else None
    )
    checkpoint_lock = asyncio.Lock()
    done_count = len(outcomes)
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

    async def _run_one(trial_index: int, trial: PlanTrial) -> tuple[int, PlanTrial, TrialOutcome]:
        nonlocal checkpoint
        key = _trial_key(trial)
        if resume:
            async with checkpoint_lock:
                checkpoint["in_progress"][key] = {
                    "task_id": trial.task_id,
                    "agent_id": trial.agent_id,
                    "sample_id": trial.sample_id,
                    "started_at_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
                }
                _save_checkpoint(base_dir, checkpoint_key, checkpoint)

        if renderer:
            renderer.render_trial_start(trial, trial_index, total)
        _log(
            f"trial_start idx={trial_index}/{total} task={trial.task_id} agent={trial.agent_id} variant={trial.variant_id} sample={trial.sample_id}"
        )

        def _on_runtime_event(event: dict[str, Any]) -> None:
            raw = dict(event or {})
            normalized = normalize_ui_event(
                raw,
                run_id=run_id,
                ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
                default_task_id=trial.task_id,
                default_agent_id=trial.agent_id,
                default_variant_id=trial.variant_id,
            )
            task_monitor.apply_event(normalized)
            evt = normalized.to_dict()
            persisted_evt = _record_event(evt, trial=trial)
            _log(f"event {json.dumps(persisted_evt, ensure_ascii=False)}")
            if renderer and hasattr(renderer, "render_runtime_event"):
                renderer.render_runtime_event(evt)

        request = TrialRequest(
            task=trial.task,
            agent=trial.agent,
            scorer=scorer,
            sample=trial.sample,
            tools=tool_specs,
            sandbox_runtime=shared_sandbox_runtime,
            on_event=_on_runtime_event,
        )
        async with scheduler.running_trial_slot():
            partial = await execute_agent_phase(request)
        async with scheduler.scoring_slot():
            outcome = await score_trial_phase(request, partial)

        if resume:
            async with checkpoint_lock:
                completed[key] = _to_serializable_outcome(outcome)
                checkpoint["completed"] = completed
                checkpoint["in_progress"].pop(key, None)
                checkpoint["failed_keys"] = sorted(
                    k
                    for k, v in completed.items()
                    if v.get("task_result", {}).get("status")
                    in {"error", "limit_exceeded", "cancelled"}
                )
                _save_checkpoint(base_dir, checkpoint_key, checkpoint)
        return trial_index, trial, outcome

    async def _bounded_run(trial_index: int, trial: PlanTrial) -> tuple[int, PlanTrial, TrialOutcome]:
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
        return await _run_one(trial_index, trial)

    interaction_stop = asyncio.Event()

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

    futures = [
        asyncio.create_task(_bounded_run(i, trial))
        for i, trial in enumerate(executable_trials, start=len(outcomes) + 1)
    ]

    try:
        for fut in asyncio.as_completed(futures):
            i, trial, outcome = await fut
            outcomes.append(outcome)
            done_count += 1

            status = outcome.task_result.status.value
            if status == "success":
                success += 1
            elif status == "incorrect":
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
                f"trial_finish idx={i}/{total} task={trial.task_id} agent={trial.agent_id} variant={trial.variant_id} sample={trial.sample_id} status={status}"
            )
    finally:
        interaction_stop.set()
        if interaction_task is not None:
            interaction_task.cancel()
            try:
                await interaction_task
            except asyncio.CancelledError:
                pass
        if input_pump is not None:
            input_pump.stop()

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
        "task_monitor": _task_monitor_rows(task_monitor, model_by_trial_key=_trial_models(plan)),
    }
    _log(f"summary {json.dumps(summary.__dict__, ensure_ascii=False)}")
    event_writer.close()
    artifacts_dir = _write_artifacts(
        base_dir=base_dir,
        run_id=run_id,
        outcomes=outcomes,
        plan=plan,
        summary=summary,
        rerun_command=rerun_cmd,
        out_dir=artifacts_dir_live,
        run_log_lines=run_log_lines,
        event_rows=event_rows,
        profiling=profiling,
        experiment_id=str(experiment_id),
        event_stream_mode="live_append",
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


async def run_eval(
    path: str | Path,
    *,
    task_filter: list[str] | None = None,
    agent_filter: list[str] | None = None,
    variant_filter: list[str] | None = None,
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
    max_trials: int | None = None,
    max_sandboxes: int | None = None,
    max_model_calls: int | None = None,
    experiment_id: str | None = None,
    on_run_bootstrap: Callable[[EvalRunBootstrap], None] | None = None,
) -> EvalRunResult:
    entry_path = Path(path).resolve()
    base_dir, project_config, _code = _resolve_project_entry(entry_path)
    components = load_project_components(entry_path, require_task_file=True)
    return await run_eval_with_components(
        entry_path=entry_path,
        base_dir=base_dir,
        tasks=components.tasks,
        agents=components.agents,
        scorer=components.scorers[0],
        tool_specs=components.tool_specs,
        task_filter=task_filter,
        agent_filter=agent_filter,
        variant_filter=variant_filter,
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
        max_trials=max_trials,
        max_sandboxes=max_sandboxes,
        max_model_calls=max_model_calls,
        project_config=project_config,
        experiment_id=experiment_id,
        on_run_bootstrap=on_run_bootstrap,
    )
