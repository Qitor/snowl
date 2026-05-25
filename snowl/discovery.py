"""Component discovery — autodetect Task, Agent, Scorer, and ToolSpec instances from user modules.

Framework role:
- Loads user Python modules (task.py, agent.py, scorer.py, tool.py) and discovers all
  protocol-conforming instances using decorator-based and fallback introspection.
- Validates uniqueness constraints (task_id, agent_id+variant_id, scorer_id) and raises
  ``SnowlValidationError`` on conflicts.
- Provides ``load_project_components`` as the primary entry point used by eval and bench commands.

Change guardrails:
- Discovery semantics are contract-defining; changes here affect what users can declare.
- Keep the decorator-first / fallback-second ordering stable.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, TypeVar

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
from snowl.project_config import (
    ProjectCodeConfig,
    ProjectConfig,
    find_project_file,
    load_project_config,
)


@dataclass(frozen=True)
class ProjectComponents:
    tasks: list[Task]
    agents: list[Agent]
    scorers: list[Scorer]
    tool_specs: list[ToolSpec]
    solvers: list[Any] = field(default_factory=list)
    hooks: list[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Project config helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

def _load_module(module_name: str, file_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise SnowlValidationError(f"Failed to load module from '{file_path}'.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Task discovery
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Agent discovery
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Scorer discovery
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Solver discovery
# ---------------------------------------------------------------------------

def _discover_solvers(module: ModuleType) -> list[Any]:
    """Discover Solver instances from a module."""
    from snowl.core.solver import Solver

    strict_ids = _discovery_strict_ids_enabled()
    solvers: list[Any] = []
    fallback_found = False
    object_seen: set[int] = set()
    id_sources: dict[str, str] = {}

    for name, value, decl in _iter_decorated_values(module, "solver"):
        if isinstance(value, (list, tuple, set)):
            items = list(value)
        else:
            items = [value]
        for item in items:
            if not isinstance(item, Solver) and not callable(item):
                raise SnowlValidationError(
                    f"Decorated solver declaration '{name}' did not resolve to Solver or callable."
                )
            if id(item) in object_seen:
                continue
            sid = getattr(item, "solver_id", name)
            if isinstance(sid, str) and sid in id_sources:
                raise SnowlValidationError(
                    f"Duplicate solver_id '{sid}' discovered between {id_sources[sid]} "
                    f"and decorated declaration '{name}'."
                )
            object_seen.add(id(item))
            if isinstance(sid, str):
                id_sources[sid] = f"decorated declaration '{name}'"
            solvers.append(item)

    for name, value in _iter_module_values(module):
        if has_declaration(value, kind="solver"):
            continue
        if inspect.isclass(value):
            continue
        if isinstance(value, Solver) or (callable(value) and hasattr(value, "solver_id")):
            fallback_found = True
            if id(value) in object_seen:
                continue
            sid = getattr(value, "solver_id", name)
            solvers.append(value)
            object_seen.add(id(value))
            if isinstance(sid, str):
                id_sources[sid] = f"fallback object '{name}'"

    if strict_ids and fallback_found:
        raise SnowlValidationError(
            "SNOWL_DISCOVERY_STRICT_IDS=1 requires decorator-based declarations. "
            "Fallback solver objects were found; mark them with @solver(...)."
        )
    return solvers


# ---------------------------------------------------------------------------
# Hooks discovery
# ---------------------------------------------------------------------------

def _discover_hooks(module: ModuleType) -> list[Any]:
    """Discover TrialHooks instances from a module."""
    from snowl.core.hooks import TrialHooks

    strict_ids = _discovery_strict_ids_enabled()
    hooks_list: list[Any] = []
    fallback_found = False
    object_seen: set[int] = set()

    for name, value, decl in _iter_decorated_values(module, "hooks"):
        if id(value) in object_seen:
            continue
        hooks_list.append(value)
        object_seen.add(id(value))

    for name, value in _iter_module_values(module):
        if has_declaration(value, kind="hooks"):
            continue
        if inspect.isclass(value):
            continue
        if isinstance(value, TrialHooks) or (callable(value) and hasattr(value, "hooks_id")):
            fallback_found = True
            if id(value) in object_seen:
                continue
            hooks_list.append(value)
            object_seen.add(id(value))

    if strict_ids and fallback_found:
        raise SnowlValidationError(
            "SNOWL_DISCOVERY_STRICT_IDS=1 requires decorator-based declarations. "
            "Fallback hooks objects were found; mark them with @hooks(...)."
        )
    return hooks_list


# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ID selection helper
# ---------------------------------------------------------------------------

TItem = TypeVar("TItem")


def _select_by_id(items: list[TItem], ids: list[str] | None, id_getter) -> list[TItem]:
    if not ids:
        return items
    id_set = {x.strip() for x in ids if x.strip()}
    selected = [item for item in items if id_getter(item) in id_set]
    return selected


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def load_project_components(
    path: str | Path,
    *,
    require_task_file: bool = True,
) -> ProjectComponents:
    base_dir, project_config, code = _resolve_project_entry(path)

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
    solvers = _discover_solvers(agent_module)
    hooks_list = _discover_hooks(agent_module)

    # Apply declarative agent_type from project.yml to all discovered agents
    agent_type = None
    agent_config = None
    if project_config is not None and project_config.eval is not None:
        agent_type = project_config.eval.agent_type
        agent_config = project_config.eval.agent_config

    # Auto-infer agent_type from benchmark middleware_hints when not explicitly set
    if not agent_type and tasks:
        for task in tasks:
            maybe_meta = getattr(task, "metadata", None) or {}
            if isinstance(maybe_meta, dict):
                bench_name = maybe_meta.get("benchmark") or maybe_meta.get("benchmark_name")
                if bench_name:
                    try:
                        from snowl.benchmarks.registry import get_default_benchmark_registry
                        registry = get_default_benchmark_registry()
                        for entry in registry.list():
                            if entry.info.name == bench_name and entry.info.middleware_hints:
                                agent_type = entry.info.middleware_hints.get("type")
                                if not agent_config and agent_type:
                                    agent_config = {k: v for k, v in entry.info.middleware_hints.items() if k != "type"}
                                break
                    except Exception:
                        pass
                    break
    if agent_type:
        from snowl.core.agent_variant import AgentVariant, AgentVariantAdapter, bind_agent_variant
        updated_agents = []
        for agent in agents:
            if isinstance(agent, AgentVariantAdapter):
                # Create new adapter with updated execution_mode
                updated = AgentVariantAdapter(
                    agent=agent.agent,
                    agent_id=agent.agent_id,
                    variant_id=agent.variant_id,
                    model=agent.model,
                    params=dict(agent.params),
                    provenance=dict(agent.provenance),
                    execution_mode=agent_type,
                    middleware_config=dict(agent_config or {}),
                )
                updated_agents.append(updated)
            else:
                # Set execution_mode attribute on plain agent objects
                try:
                    setattr(agent, "execution_mode", agent_type)
                    if agent_config:
                        setattr(agent, "middleware_config", agent_config)
                except Exception:
                    pass
                updated_agents.append(agent)
        agents = updated_agents

    # Apply framework adapter from project.yml
    framework = None
    if project_config is not None and project_config.eval is not None:
        framework = project_config.eval.framework
    if framework:
        from snowl.adapters.registry import get_default_adapter_registry
        adapter_registry = get_default_adapter_registry()
        if adapter_registry.has(framework):
            adapter = adapter_registry.get(framework)
            agent_config_for_adapter = dict(agent_config or {})
            wrapped_agents = []
            for discovered_agent in agents:
                # For AgentVariantAdapter, wrap the inner agent
                inner = discovered_agent
                if isinstance(discovered_agent, AgentVariantAdapter):
                    inner = discovered_agent.agent
                try:
                    wrapped = adapter.wrap(inner, **agent_config_for_adapter)
                    wrapped_agents.append(wrapped)
                except Exception as exc:
                    raise SnowlValidationError(
                        f"Failed to wrap agent with {framework} adapter: {exc}"
                    ) from exc
            agents = wrapped_agents

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
        solvers=solvers,
        hooks=hooks_list,
    )
