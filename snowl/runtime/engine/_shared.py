"""Shared data classes and cross-phase helper functions for the engine package.

This module is the single source of truth for:
- Trial data classes: TrialLimits, TrialRequest, TrialOutcome, PartialTrialResult,
  PreparedTrial, FinalizedTrialArtifacts.
- Private helpers used across prepare, execute, score, and finalize phases.

Framework role:
- Transforms one ``TrialRequest`` into normalized ``TaskResult``, score map, trace
  payload, and teardown diagnostics.
- Hosts phase helpers used by runtime call sites and tests.

Change guardrails:
- Any change to status mapping, payload shape, or error normalization impacts
  scorers, artifacts, and UI contracts.
- Keep task-result schema compatibility unless the broader contract is
  intentionally versioned.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from snowl.core.agent import Agent, AgentContext, AgentState, StopReason, validate_agent
from snowl.core.env import ensure_tool_ops_compatible, validate_env_spec
from snowl.core.scorer import ScoreContext, Scorer, validate_scorer, validate_scores
from snowl.core.task import Task, validate_task
from snowl.core.task_result import ArtifactRef, ErrorInfo, TaskResult, TaskStatus, Timing, Usage
from snowl.core.tool import ToolSpec, resolve_tool_spec
from snowl.envs.sandbox_runtime import SandboxRuntime, WarmPoolSandboxRuntime
from snowl.errors import SnowlValidationError
from snowl.runtime.container_lifecycle import RuntimeContainerLifecycleManager
from snowl.runtime.container_contract import resolve_runtime_container_spec
from snowl.runtime.container_runtime import ContainerPrepareResult, ContainerRuntime
from snowl.runtime.resource_scheduler import TaskExecutionPlan, TrialDescriptor
from snowl.runtime.workspace import (
    RuntimeWorkspaceManager,
    RuntimeWorkspaceSession,
    diff_workspace,
    resolve_workspace_spec,
    snapshot_workspace,
)
from snowl.ui.contracts import build_score_explanations

_DEFAULT_SANDBOX_RUNTIME = WarmPoolSandboxRuntime()


@dataclass(frozen=True)
class TrialLimits:
    max_steps: int | None = None
    time_limit_seconds: float | None = None
    token_limit: int | None = None


@dataclass(frozen=True)
class TrialRequest:
    task: Task
    agent: Agent
    sample: Mapping[str, Any]
    seed: int | None = None
    tools: Sequence[Any] | None = None
    scorer: Scorer | None = None
    scorers: tuple[Scorer, ...] = ()
    sandbox_runtime: SandboxRuntime | None = None
    limits: TrialLimits = TrialLimits()
    on_event: Callable[[dict[str, Any]], None] | None = None
    execution_plan: TaskExecutionPlan | None = None
    trial_descriptor: TrialDescriptor | None = None
    container_lifecycle: RuntimeContainerLifecycleManager | None = None
    run_id: str | None = None
    trial_id: str | None = None
    execution_mode: str = "native"  # "native" | "emulated" | "stateful"
    middleware_config: dict[str, Any] = field(default_factory=dict)
    solver_chain: Any | None = None
    mcp_servers: list[dict[str, Any]] | None = None  # From project.yml
    epochs: int = 1  # Number of times to run each sample
    score_reducer: Any | None = None  # ScoreReducer instance

    def __post_init__(self) -> None:
        # Backward compat: if scorers empty but scorer provided, wrap it.
        if not self.scorers and self.scorer is not None:
            object.__setattr__(self, "scorers", (self.scorer,))
        # Inherit execution_mode from agent if not explicitly set
        if self.execution_mode == "native":
            agent_mode = getattr(self.agent, "execution_mode", None)
            if agent_mode and agent_mode != "native":
                object.__setattr__(self, "execution_mode", agent_mode)
        # Inherit solver_chain from agent if not explicitly set
        if self.solver_chain is None:
            agent_chain = getattr(self.agent, "solver_chain", None)
            if agent_chain is not None:
                object.__setattr__(self, "solver_chain", agent_chain)


@dataclass(frozen=True)
class TrialOutcome:
    task_result: TaskResult
    scores: dict[str, Any]
    trace: dict[str, Any]


@dataclass(frozen=True)
class PartialTrialResult:
    task_result: TaskResult
    trace: dict[str, Any]
    score_context: ScoreContext


@dataclass(frozen=True)
class PreparedTrial:
    request: TrialRequest
    started_ms: int
    sample_id: str | None
    variant_id: str
    variant_model: str | None
    state: AgentState
    context: AgentContext
    resolved_tool_specs: Sequence[ToolSpec]
    sandbox_runtime: SandboxRuntime
    container_runtime: ContainerRuntime
    container_prepare: ContainerPrepareResult
    workspace_session: RuntimeWorkspaceSession | None = None
    prepared_sandbox: Any | None = None
    original_max_steps: int | None = None
    failed_partial: PartialTrialResult | None = None
    mcp_manager: Any | None = None


@dataclass(frozen=True)
class FinalizedTrialArtifacts:
    teardown: dict[str, Any] | None
    container_close: dict[str, Any] | None


def _initial_messages(sample: Mapping[str, Any]) -> list[dict[str, Any]]:
    if "messages" in sample and isinstance(sample["messages"], list):
        return [dict(message) for message in sample["messages"]]

    if "input" in sample:
        return [{"role": "user", "content": str(sample["input"])}]

    raise SnowlValidationError("Sample must contain either 'messages' or 'input'.")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(v) for v in value]
    return str(value)


def _extract_sample_input(sample: Mapping[str, Any]) -> dict[str, Any]:
    if "messages" in sample and isinstance(sample["messages"], list):
        return {"messages": _json_safe(sample["messages"])}
    if "input" in sample:
        return {"input": _json_safe(sample["input"])}
    return {"sample": _json_safe(sample)}


def _get_extra_payload_keys(task: Task) -> list[str]:
    """Look up extra_payload_keys from benchmark registry via task metadata."""
    metadata = getattr(task, "metadata", None)
    if not isinstance(metadata, Mapping):
        return []
    bench_name = str(metadata.get("benchmark") or metadata.get("benchmark_name") or "").strip().lower()
    if not bench_name or bench_name == "custom":
        return []
    try:
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        for entry in registry.list():
            if entry.info.name == bench_name:
                return entry.info.runtime_hints.get("extra_payload_keys", [])
    except Exception:
        pass
    return []


def _benchmark_has_canary(task: Task) -> bool:
    """Check if the benchmark declares has_canary=True."""
    metadata = getattr(task, "metadata", None)
    if not isinstance(metadata, Mapping):
        return False
    bench_name = str(metadata.get("benchmark") or metadata.get("benchmark_name") or "").strip().lower()
    if not bench_name or bench_name == "custom":
        return False
    try:
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        for entry in registry.list():
            if entry.info.name == bench_name:
                return entry.info.has_canary
    except Exception:
        pass
    return False


def _sample_declared_tool_names(sample: Mapping[str, Any]) -> list[str]:
    metadata = sample.get("metadata")
    if not isinstance(metadata, Mapping):
        return []
    raw = metadata.get("tool_names")
    if raw is None:
        raw = metadata.get("target_functions")
    if raw is None:
        return []
    if isinstance(raw, str):
        names = [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        names = [str(item) for item in raw]
    else:
        return []
    return [name.strip() for name in names if name.strip()]


def _sample_declared_tool_schemas(sample: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadata = sample.get("metadata")
    if not isinstance(metadata, Mapping):
        return []
    raw = metadata.get("tool_schemas")
    if raw is None:
        raw = metadata.get("tools")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return []
    schemas: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        schema = dict(item)
        if schema.get("type") == "function" and isinstance(schema.get("function"), Mapping):
            fn = dict(schema["function"])
        else:
            fn = schema
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        parameters = fn.get("parameters")
        if not isinstance(parameters, Mapping):
            parameters = {"type": "object", "properties": {}, "additionalProperties": False}
        schemas.append(
            {
                "name": name,
                "description": str(fn.get("description") or f"Tool '{name}'."),
                "parameters": dict(parameters),
                "required_ops": tuple(str(op) for op in (fn.get("required_ops") or ()) if str(op).strip()),
                "result": fn.get("result"),
            }
        )
    return schemas


def _build_dynamic_tool_specs(sample: Mapping[str, Any]) -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for schema in _sample_declared_tool_schemas(sample):
        name = str(schema["name"])
        result_value = schema.get("result")

        def _recording_tool(_result: Any = result_value, _name: str = name, **kwargs: Any) -> Any:
            if _result is not None:
                return _result
            return {"ok": True, "tool": _name, "arguments": kwargs}

        specs.append(
            ToolSpec(
                name=name,
                description=str(schema.get("description") or f"Tool '{name}'."),
                parameters=dict(schema.get("parameters") or {"type": "object", "properties": {}, "additionalProperties": False}),
                callable=_recording_tool,
                required_ops=tuple(schema.get("required_ops") or ()),
            )
        )
    return specs


def _merge_project_and_dynamic_tools(
    project_specs: Sequence[ToolSpec],
    dynamic_specs: Sequence[ToolSpec],
) -> tuple[list[ToolSpec], list[str]]:
    merged: dict[str, ToolSpec] = {spec.name: spec for spec in project_specs}
    conflicts: list[str] = []
    for spec in dynamic_specs:
        existing = merged.get(spec.name)
        if existing is not None:
            existing_schema = json.dumps(existing.parameters, sort_keys=True, ensure_ascii=True)
            new_schema = json.dumps(spec.parameters, sort_keys=True, ensure_ascii=True)
            if existing_schema != new_schema:
                conflicts.append(spec.name)
            continue
        merged[spec.name] = spec
    return list(merged.values()), conflicts


def _select_sample_tools(
    specs: Sequence[ToolSpec],
    sample: Mapping[str, Any],
) -> tuple[list[ToolSpec], list[str]]:
    requested_names = _sample_declared_tool_names(sample)
    if not requested_names:
        return list(specs), []
    by_name = {spec.name: spec for spec in specs}
    missing = [name for name in requested_names if name not in by_name]
    selected = [by_name[name] for name in requested_names if name in by_name]
    return selected, missing


def _sample_preview_text(sample: Mapping[str, Any], *, max_chars: int = 240) -> str:
    text = ""
    if "input" in sample:
        text = str(sample.get("input") or "")
    elif "messages" in sample and isinstance(sample["messages"], list):
        user_chunks: list[str] = []
        for msg in sample["messages"]:
            if not isinstance(msg, Mapping):
                continue
            role = str(msg.get("role") or "")
            if role.lower() != "user":
                continue
            user_chunks.append(str(msg.get("content") or ""))
        text = "\n".join([chunk for chunk in user_chunks if chunk])
    text = text.strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "\u2026"


def _status_from_stop_reason(stop_reason: StopReason | None) -> TaskStatus:
    if stop_reason == StopReason.CANCELLED:
        return TaskStatus.CANCELLED

    if stop_reason in {StopReason.MAX_STEPS, StopReason.LIMIT_EXCEEDED}:
        return TaskStatus.LIMIT_EXCEEDED

    if stop_reason == StopReason.ERROR:
        return TaskStatus.ERROR

    return TaskStatus.SUCCESS


def _build_score_context(request: TrialRequest, *, sample_id: str | None) -> ScoreContext:
    return ScoreContext(
        task_id=request.task.task_id,
        agent_id=getattr(request.agent, "agent_id"),
        sample_id=sample_id,
        task_metadata=request.task.metadata,
        sample_metadata=dict(request.sample.get("metadata", {})),
    )


def _score_context_for_prepared(
    prepared: PreparedTrial,
    *,
    extra_sample_metadata: Mapping[str, Any] | None = None,
) -> ScoreContext:
    sample_meta = dict(prepared.request.sample.get("metadata", {}) or {})
    context_sample = prepared.context.metadata.get("sample")
    if isinstance(context_sample, Mapping):
        context_meta = context_sample.get("metadata")
        if isinstance(context_meta, Mapping):
            sample_meta.update(dict(context_meta))
    sample_meta.update(dict(extra_sample_metadata or {}))
    return ScoreContext(
        task_id=prepared.request.task.task_id,
        agent_id=getattr(prepared.request.agent, "agent_id"),
        sample_id=prepared.sample_id,
        task_metadata=prepared.request.task.metadata,
        sample_metadata=sample_meta,
    )


def _emit_factory(request: TrialRequest) -> Callable[[dict[str, Any]], None]:
    def _emit(event: dict[str, Any]) -> None:
        if request.on_event is None:
            return
        try:
            request.on_event(dict(event))
        except Exception:
            return

    return _emit


def _error_partial(
    request: TrialRequest,
    *,
    started_ms: int,
    sample_id: str | None,
    variant_id: str,
    variant_model: str | None,
    code: str,
    message: str,
    phase: str,
    trace_event: str,
) -> PartialTrialResult:
    ended = int(time.time() * 1000)
    error = ErrorInfo(code=code, message=message, retryable=False)
    error_payload: dict[str, Any] = {
        "stop_reason": StopReason.ERROR.value,
        "phase": phase,
        "variant_id": variant_id,
        "model": variant_model,
    }
    # Propagate task metadata keys into error payload for aggregation
    task_meta = request.task.metadata if isinstance(request.task.metadata, dict) else {}
    for _mk in ("benchmark", "domain", "benchmark_type", "family", "primary_metric"):
        if _mk in task_meta and _mk not in error_payload:
            error_payload[_mk] = task_meta[_mk]
    # Propagate model metadata from variant params
    variant_params = getattr(request.agent, "params", None)
    if isinstance(variant_params, dict) and "model_metadata" in variant_params:
        error_payload["model_metadata"] = variant_params["model_metadata"]
    task_result = TaskResult(
        task_id=request.task.task_id,
        agent_id=getattr(request.agent, "agent_id"),
        sample_id=sample_id,
        seed=request.seed,
        status=TaskStatus.ERROR,
        final_output={},
        timing=Timing(started_at_ms=started_ms, ended_at_ms=ended, duration_ms=max(0, ended - started_ms)),
        usage=Usage(),
        error=error,
        payload=error_payload,
    )
    trace = {
        "trace_events": [{"event": trace_event, "message": message}],
        "actions": [],
        "observations": [],
        "stop_reason": StopReason.ERROR.value,
    }
    _emit_factory(request)(
        {
            "event": "runtime.trial.error",
            "phase": phase,
            "code": code,
            "message": message,
            "task_id": request.task.task_id,
            "agent_id": getattr(request.agent, "agent_id"),
            "variant_id": variant_id,
            "sample_id": sample_id,
        }
    )
    return PartialTrialResult(
        task_result=task_result,
        trace=trace,
        score_context=_build_score_context(request, sample_id=sample_id),
    )
