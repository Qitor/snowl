"""Execution-plane implementation for single-trial prepare, execute, score, and finalize phases.

Framework role:
- Transforms one `TrialRequest` into normalized `TaskResult`, score map, trace payload, and teardown diagnostics.
- Hosts phase helpers used by runtime call sites and tests (`prepare_trial_phase`, `execute_agent_phase`, `score_trial_phase`, `finalize_trial_phase`).

Runtime/usage wiring:
- `execute_trial` runs full prepare->execute->score->finalize for callers that want one-shot semantics.
- Main eval loop currently calls execute+score helpers directly, so finalize semantics must be reasoned about with `snowl.eval` together.
- Key top-level symbols in this file: `TrialLimits`, `TrialRequest`, `TrialOutcome`, `PartialTrialResult`, `PreparedTrial`, `FinalizedTrialArtifacts`.

Change guardrails:
- Any change to status mapping, payload shape, or error normalization impacts scorers, artifacts, and UI contracts.
- Keep task-result schema compatibility unless the broader contract is intentionally versioned.
"""

from __future__ import annotations

import asyncio
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

    def __post_init__(self) -> None:
        # Backward compat: if scorers empty but scorer provided, wrap it.
        if not self.scorers and self.scorer is not None:
            object.__setattr__(self, "scorers", (self.scorer,))
        # Inherit execution_mode from agent if not explicitly set
        if self.execution_mode == "native":
            agent_mode = getattr(self.agent, "execution_mode", None)
            if agent_mode and agent_mode != "native":
                object.__setattr__(self, "execution_mode", agent_mode)


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
    return text[: max_chars - 1] + "…"


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


async def prepare_trial_phase(request: TrialRequest) -> PreparedTrial:
    """Prepare env/container/sandbox state for a trial."""

    validate_task(request.task)
    validate_env_spec(request.task.env_spec)
    validate_agent(request.agent)
    validate_scorer(request.scorer)

    started = int(time.time() * 1000)
    sample_id = str(request.sample.get("id")) if request.sample.get("id") is not None else None
    variant_id = str(getattr(request.agent, "variant_id", "default"))
    variant_model = getattr(request.agent, "model", None)
    emit = _emit_factory(request)
    sample_for_runtime = dict(request.sample)

    emit(
        {
            "event": "runtime.trial.start",
            "phase": "prepare",
            "task_id": request.task.task_id,
            "agent_id": getattr(request.agent, "agent_id"),
            "variant_id": variant_id,
            "sample_id": sample_id,
            "message": _sample_preview_text(request.sample),
            "payload": {
                "sample_input": _extract_sample_input(request.sample),
            },
        }
    )

    state = AgentState(messages=_initial_messages(request.sample))
    context = AgentContext(
        task_id=request.task.task_id,
        sample_id=sample_id,
        metadata={
            "sample": sample_for_runtime,
            "task_metadata": request.task.metadata,
            "variant_id": variant_id,
            "model": variant_model,
            "__snowl_emit_event": emit,
        },
    )

    workspace_session: RuntimeWorkspaceSession | None = None
    try:
        pre_container_spec = resolve_runtime_container_spec(
            task_metadata=request.task.metadata,
            sample=request.sample,
        )
        workspace_spec = resolve_workspace_spec(
            task_metadata=request.task.metadata,
            sample=request.sample,
            container_startup=pre_container_spec.startup,
            container_workspace=pre_container_spec.workspace,
        )
        workspace_session = RuntimeWorkspaceManager(
            run_id=request.run_id,
            trial_id=request.trial_id,
            task_id=request.task.task_id,
            sample_id=sample_id,
            spec=workspace_spec,
        ).prepare()
        if workspace_session is not None:
            sample_meta = dict(sample_for_runtime.get("metadata", {}) or {})
            runtime_container = dict(sample_meta.get("runtime_container", {}) or {})
            startup = dict(runtime_container.get("startup", {}) or {})
            workspace_contract = dict(runtime_container.get("workspace", {}) or {})
            startup["workspace_dir"] = workspace_session.workspace_dir
            workspace_contract["workspace_dir"] = workspace_session.workspace_dir
            runtime_container["startup"] = startup
            runtime_container["workspace"] = workspace_contract
            sample_meta.update(
                {
                    "runtime_container": runtime_container,
                    "workspace_dir": workspace_session.workspace_dir,
                    "workspace_before": dict(workspace_session.before),
                    "workspace_spec": workspace_session.spec.to_metadata(),
                }
            )
            sample_for_runtime["metadata"] = sample_meta
            context.metadata["sample"] = sample_for_runtime
            context.metadata["__snowl_workspace"] = {
                "workspace_dir": workspace_session.workspace_dir,
                "before": dict(workspace_session.before),
            }
            emit(
                {
                    "event": "runtime.workspace.prepared",
                    "phase": "prepare",
                    "workspace_dir": workspace_session.workspace_dir,
                    "file_count": len(workspace_session.before),
                }
            )
    except Exception as exc:
        container_runtime = ContainerRuntime(
            run_id=request.run_id,
            trial_id=request.trial_id,
            task_id=request.task.task_id,
            agent_id=getattr(request.agent, "agent_id"),
            variant_id=variant_id,
            task_env_type=request.task.env_spec.env_type,
            task_metadata=request.task.metadata,
            sample=sample_for_runtime,
            emit=emit,
            lifecycle_manager=request.container_lifecycle,
        )
        return PreparedTrial(
            request=request,
            started_ms=started,
            sample_id=sample_id,
            variant_id=variant_id,
            variant_model=variant_model,
            state=state,
            context=context,
            resolved_tool_specs=[],
            sandbox_runtime=request.sandbox_runtime or _DEFAULT_SANDBOX_RUNTIME,
            container_runtime=container_runtime,
            container_prepare=ContainerPrepareResult(
                session=None,
                requires_container=False,
                requires_build=False,
                spec_hash=None,
                prepare_provider_ids=(),
                metadata={},
            ),
            workspace_session=workspace_session,
            failed_partial=_error_partial(
                request,
                started_ms=started,
                sample_id=sample_id,
                variant_id=variant_id,
                variant_model=variant_model,
                code="workspace_prepare_error",
                message=str(exc),
                phase="prepare",
                trace_event="runtime.workspace.error",
            ),
        )

    container_runtime = ContainerRuntime(
        run_id=request.run_id,
        trial_id=request.trial_id,
        task_id=request.task.task_id,
        agent_id=getattr(request.agent, "agent_id"),
        variant_id=variant_id,
        task_env_type=request.task.env_spec.env_type,
        task_metadata=request.task.metadata,
        sample=sample_for_runtime,
        emit=emit,
        lifecycle_manager=request.container_lifecycle,
    )
    container_prepare = ContainerPrepareResult(
        session=None,
        requires_container=False,
        requires_build=False,
        spec_hash=None,
        prepare_provider_ids=(),
        metadata={},
    )
    try:
        container_prepare = await container_runtime.prepare_phase()
        if container_prepare.session is not None:
            context.metadata["__snowl_container_session"] = container_prepare.session
        if container_prepare.container_spec is not None:
            context.metadata["__snowl_runtime_container_spec"] = container_prepare.container_spec.to_metadata()
    except Exception as exc:
        return PreparedTrial(
            request=request,
            started_ms=started,
            sample_id=sample_id,
            variant_id=variant_id,
            variant_model=variant_model,
            state=state,
            context=context,
            resolved_tool_specs=[],
            sandbox_runtime=request.sandbox_runtime or _DEFAULT_SANDBOX_RUNTIME,
            container_runtime=container_runtime,
            container_prepare=container_prepare,
            workspace_session=None,
            failed_partial=_error_partial(
                request,
                started_ms=started,
                sample_id=sample_id,
                variant_id=variant_id,
                variant_model=variant_model,
                code="container_runtime_error",
                message=str(exc),
                phase="prepare",
                trace_event="runtime.container.error",
            ),
        )

    resolved_tool_specs: list[ToolSpec] = []
    if request.tools:
        resolved_tool_specs = [resolve_tool_spec(t) for t in request.tools]
    dynamic_tool_specs = _build_dynamic_tool_specs(request.sample)
    resolved_tool_specs, dynamic_tool_conflicts = _merge_project_and_dynamic_tools(
        resolved_tool_specs,
        dynamic_tool_specs,
    )
    if dynamic_tool_conflicts:
        return PreparedTrial(
            request=request,
            started_ms=started,
            sample_id=sample_id,
            variant_id=variant_id,
            variant_model=variant_model,
            state=state,
            context=context,
            resolved_tool_specs=resolved_tool_specs,
            sandbox_runtime=request.sandbox_runtime or _DEFAULT_SANDBOX_RUNTIME,
            container_runtime=container_runtime,
            container_prepare=container_prepare,
            workspace_session=workspace_session,
            failed_partial=_error_partial(
                request,
                started_ms=started,
                sample_id=sample_id,
                variant_id=variant_id,
                variant_model=variant_model,
                code="sample_tool_schema_conflict",
                message="Sample dynamic tool schemas conflict with project tools: "
                + ", ".join(dynamic_tool_conflicts),
                phase="prepare",
                trace_event="runtime.tool.error",
            ),
        )
    resolved_tool_specs, missing_sample_tools = _select_sample_tools(
        resolved_tool_specs,
        request.sample,
    )
    if missing_sample_tools:
        return PreparedTrial(
            request=request,
            started_ms=started,
            sample_id=sample_id,
            variant_id=variant_id,
            variant_model=variant_model,
            state=state,
            context=context,
            resolved_tool_specs=resolved_tool_specs,
            sandbox_runtime=request.sandbox_runtime or _DEFAULT_SANDBOX_RUNTIME,
            container_runtime=container_runtime,
            container_prepare=container_prepare,
            workspace_session=workspace_session,
            failed_partial=_error_partial(
                request,
                started_ms=started,
                sample_id=sample_id,
                variant_id=variant_id,
                variant_model=variant_model,
                code="sample_tool_missing",
                message="Sample requested unavailable tools: " + ", ".join(missing_sample_tools),
                phase="prepare",
                trace_event="runtime.tool.error",
            ),
        )
    context.metadata["available_tool_names"] = [spec.name for spec in resolved_tool_specs]

    required_ops = {op for spec in resolved_tool_specs for op in spec.required_ops}
    provided_ops = set(request.task.env_spec.provided_ops)
    missing_ops = ensure_tool_ops_compatible(required_ops, provided_ops)
    if missing_ops:
        return PreparedTrial(
            request=request,
            started_ms=started,
            sample_id=sample_id,
            variant_id=variant_id,
            variant_model=variant_model,
            state=state,
            context=context,
            resolved_tool_specs=resolved_tool_specs,
            sandbox_runtime=request.sandbox_runtime or _DEFAULT_SANDBOX_RUNTIME,
            container_runtime=container_runtime,
            container_prepare=container_prepare,
            workspace_session=workspace_session,
            failed_partial=_error_partial(
                request,
                started_ms=started,
                sample_id=sample_id,
                variant_id=variant_id,
                variant_model=variant_model,
                code="env_ops_mismatch",
                message=(
                    "Tool requires unsupported env ops: "
                    + ", ".join(sorted(missing_ops))
                    + f". Env provides: {', '.join(sorted(provided_ops)) or '(none)'}."
                ),
                phase="prepare",
                trace_event="runtime.validation_error",
            ),
        )

    original_max_steps = None
    if request.limits.max_steps is not None and hasattr(request.agent, "max_steps"):
        try:
            original_max_steps = getattr(request.agent, "max_steps")
            setattr(request.agent, "max_steps", request.limits.max_steps)
        except Exception:
            original_max_steps = None

    sandbox_runtime = request.sandbox_runtime or _DEFAULT_SANDBOX_RUNTIME
    prepared_sandbox = None
    try:
        if request.task.env_spec.sandbox_spec is not None:
            emit({"event": "runtime.sandbox.prepare.start", "phase": "prepare", "provider": request.task.env_spec.sandbox_spec.provider})
            prepared_sandbox = await sandbox_runtime.prepare(request.task.env_spec.sandbox_spec)
            emit(
                {
                    "event": "runtime.sandbox.prepare.done",
                    "phase": "prepare",
                    "provider": prepared_sandbox.provider,
                    "sandbox_id": prepared_sandbox.sandbox_id,
                }
            )
    except Exception as exc:
        return PreparedTrial(
            request=request,
            started_ms=started,
            sample_id=sample_id,
            variant_id=variant_id,
            variant_model=variant_model,
            state=state,
            context=context,
            resolved_tool_specs=resolved_tool_specs,
            sandbox_runtime=sandbox_runtime,
            container_runtime=container_runtime,
            container_prepare=container_prepare,
            workspace_session=workspace_session,
            original_max_steps=original_max_steps,
            failed_partial=_error_partial(
                request,
                started_ms=started,
                sample_id=sample_id,
                variant_id=variant_id,
                variant_model=variant_model,
                code="sandbox_prepare_error",
                message=str(exc),
                phase="prepare",
                trace_event="runtime.sandbox.error",
            ),
        )

    return PreparedTrial(
        request=request,
        started_ms=started,
        sample_id=sample_id,
        variant_id=variant_id,
        variant_model=variant_model,
        state=state,
        context=context,
        resolved_tool_specs=resolved_tool_specs,
        sandbox_runtime=sandbox_runtime,
        container_runtime=container_runtime,
        container_prepare=container_prepare,
        workspace_session=workspace_session,
        prepared_sandbox=prepared_sandbox,
        original_max_steps=original_max_steps,
        failed_partial=None,
    )


def _inject_execution_middleware(prepared: PreparedTrial, mode: str, config: dict[str, Any]) -> None:
    """Inject middleware chain based on execution_mode before agent.run()."""
    agent = prepared.request.agent
    if mode == "emulated":
        from snowl.tools.emulated_tool import EmulatedToolWrapper
        from snowl.tools.middleware import MiddlewareChain
        from snowl.model import OpenAICompatibleChatClient
        emulator_model = config.get("emulator_model", "gpt-4o-mini")
        # Build emulator client from provider config if available
        base_url = config.get("emulator_base_url")
        api_key = config.get("emulator_api_key")
        emulator_client = OpenAICompatibleChatClient(
            model=emulator_model,
            base_url=base_url,
            api_key=api_key,
        )
        wrapper = EmulatedToolWrapper(
            emulator_client=emulator_client,
            simulator_type=config.get("simulator_type", "std_thought"),
            num_critique_steps=config.get("num_critique_steps", 0),
        )
        # Set middleware on the agent if it supports it
        if hasattr(agent, "middlewares"):
            existing = list(agent.middlewares or [])
            existing.append(wrapper)
            agent.middlewares = existing
    elif mode == "stateful":
        from snowl.tools.stateful_executor import StatefulToolExecutor
        if hasattr(agent, "middlewares"):
            existing = list(agent.middlewares or [])
            existing.append(StatefulToolExecutor())
            # If injection_config present, also add InjectionMiddleware
            inj_config = config.get("injection_config")
            if inj_config:
                from snowl.tools.injection import build_injection_middleware_from_config
                existing.append(build_injection_middleware_from_config(inj_config))
            agent.middlewares = existing
    elif mode == "injection":
        from snowl.tools.injection import InjectionMiddleware, build_injection_middleware_from_config
        middleware = build_injection_middleware_from_config(config)
        if hasattr(agent, "middlewares"):
            existing = list(agent.middlewares or [])
            existing.append(middleware)
            agent.middlewares = existing
    elif mode == "stateful+injection":
        from snowl.tools.stateful_executor import StatefulToolExecutor
        from snowl.tools.injection import InjectionMiddleware, build_injection_middleware_from_config
        if hasattr(agent, "middlewares"):
            existing = list(agent.middlewares or [])
            existing.append(StatefulToolExecutor())
            # Injection config comes from "injection_config" sub-key if present
            inj_config = config.get("injection_config", config)
            existing.append(build_injection_middleware_from_config(inj_config))
            agent.middlewares = existing


async def execute_agent_phase(prepared: PreparedTrial | TrialRequest) -> PartialTrialResult:
    """Execute the agent/runtime phase and produce a partial trial result."""

    if isinstance(prepared, TrialRequest):
        # Callers can pass a raw request for convenience. In the main eval loop
        # this means prepare still happens inside the running-trial admission.
        prepared = await prepare_trial_phase(prepared)

    request = prepared.request
    if prepared.failed_partial is not None:
        return prepared.failed_partial

    emit = _emit_factory(request)
    error: ErrorInfo | None = None
    status = TaskStatus.SUCCESS
    state = prepared.state

    # Apply execution strategy: inject middleware based on execution_mode
    execution_mode = request.execution_mode or "native"
    if execution_mode != "native":
        _inject_execution_middleware(prepared, execution_mode, request.middleware_config)

    try:
        async def _agent_run():
            return await request.agent.run(prepared.state, prepared.context, tools=prepared.resolved_tool_specs)

        if request.limits.time_limit_seconds is not None:
            if prepared.prepared_sandbox is not None:
                state = await asyncio.wait_for(
                    prepared.sandbox_runtime.run(prepared.prepared_sandbox, _agent_run),
                    timeout=request.limits.time_limit_seconds,
                )
            else:
                state = await asyncio.wait_for(_agent_run(), timeout=request.limits.time_limit_seconds)
        else:
            if prepared.prepared_sandbox is not None:
                state = await prepared.sandbox_runtime.run(prepared.prepared_sandbox, _agent_run)
            else:
                state = await _agent_run()

        status = _status_from_stop_reason(state.stop_reason)
    except TimeoutError:
        status = TaskStatus.LIMIT_EXCEEDED
        state.stop_reason = StopReason.LIMIT_EXCEEDED
        error = ErrorInfo(code="time_limit_exceeded", message="Trial exceeded time limit.")
        emit(
            {
                "event": "runtime.trial.error",
                "phase": "execute",
                "code": error.code,
                "message": error.message,
                "task_id": request.task.task_id,
                "agent_id": getattr(request.agent, "agent_id"),
                "variant_id": prepared.variant_id,
                "sample_id": prepared.sample_id,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive catch
        status = TaskStatus.ERROR
        state.stop_reason = StopReason.ERROR
        error = ErrorInfo(code="agent_runtime_error", message=str(exc), retryable=False)
        emit(
            {
                "event": "runtime.trial.error",
                "phase": "execute",
                "code": error.code,
                "message": error.message,
                "task_id": request.task.task_id,
                "agent_id": getattr(request.agent, "agent_id"),
                "variant_id": prepared.variant_id,
                "sample_id": prepared.sample_id,
            }
        )

    output = state.output or {}
    usage_data = output.get("usage") or {}
    usage = Usage(
        input_tokens=int(usage_data.get("input_tokens", 0) or 0),
        output_tokens=int(usage_data.get("output_tokens", 0) or 0),
        total_tokens=int(usage_data.get("total_tokens", 0) or 0),
        estimated_cost_usd=None,
    )
    artifacts: list[ArtifactRef] = []
    for item in output.get("artifacts", []) or []:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        uri = str(item.get("uri") or "").strip()
        if not name or not uri:
            continue
        media_type = item.get("media_type")
        artifacts.append(
            ArtifactRef(
                name=name,
                uri=uri,
                media_type=(str(media_type) if media_type is not None else None),
            )
        )

    if request.limits.token_limit is not None and usage.total_tokens > request.limits.token_limit:
        status = TaskStatus.LIMIT_EXCEEDED
        error = ErrorInfo(
            code="token_limit_exceeded",
            message=(
                f"Trial used {usage.total_tokens} tokens, exceeds token limit "
                f"{request.limits.token_limit}."
            ),
        )
        emit(
            {
                "event": "runtime.trial.error",
                "phase": "execute",
                "code": error.code,
                "message": error.message,
                "task_id": request.task.task_id,
                "agent_id": getattr(request.agent, "agent_id"),
                "variant_id": prepared.variant_id,
                "sample_id": prepared.sample_id,
            }
        )

    ended = int(time.time() * 1000)
    payload: dict[str, Any] = {
        "stop_reason": state.stop_reason.value if state.stop_reason else None,
        "variant_id": prepared.variant_id,
        "model": prepared.variant_model,
        "sample_input": _extract_sample_input(request.sample),
    }
    # Propagate task metadata keys into payload for aggregation
    task_meta = request.task.metadata if isinstance(request.task.metadata, dict) else {}
    for _mk in ("benchmark", "domain", "benchmark_type", "family", "primary_metric"):
        if _mk in task_meta and _mk not in payload:
            payload[_mk] = task_meta[_mk]
    # Propagate model metadata from variant params
    variant_params = getattr(request.agent, "params", None)
    if isinstance(variant_params, dict) and "model_metadata" in variant_params:
        payload["model_metadata"] = variant_params["model_metadata"]
    if output.get("osworld_score") is not None:
        payload["osworld_score"] = output["osworld_score"]
    if prepared.prepared_sandbox is not None:
        payload["sandbox"] = {
            "sandbox_id": prepared.prepared_sandbox.sandbox_id,
            "spec_hash": prepared.prepared_sandbox.spec_hash,
            "provider": prepared.prepared_sandbox.provider,
            "prepare": prepared.prepared_sandbox.diagnostics,
        }
    if prepared.container_prepare.spec_hash:
        payload["container"] = {
            "spec_hash": prepared.container_prepare.spec_hash,
            "resource_id": prepared.container_prepare.resource_id,
            **dict(prepared.container_prepare.metadata),
        }

    task_result = TaskResult(
        task_id=request.task.task_id,
        agent_id=getattr(request.agent, "agent_id"),
        sample_id=prepared.sample_id,
        seed=request.seed,
        status=status,
        final_output={
            "message": output.get("message", {}),
            "content": (output.get("message", {}) or {}).get("content"),
            **({"traj": output.get("traj")} if output.get("traj") is not None else {}),
        },
        timing=Timing(
            started_at_ms=prepared.started_ms,
            ended_at_ms=ended,
            duration_ms=max(0, ended - prepared.started_ms),
        ),
        usage=usage,
        error=error,
        artifacts=artifacts,
        payload=payload,
    )
    trace = {
        "trace_events": output.get("trace_events", []),
        "actions": [
            {"action_type": a.action_type, "payload": dict(a.payload)}
            for a in state.actions
        ],
        "observations": [
            {"observation_type": o.observation_type, "payload": dict(o.payload)}
            for o in state.observations
        ],
        "stop_reason": state.stop_reason.value if state.stop_reason else None,
    }
    if prepared.prepared_sandbox is not None:
        trace["sandbox"] = {
            "sandbox_id": prepared.prepared_sandbox.sandbox_id,
            "spec_hash": prepared.prepared_sandbox.spec_hash,
            "provider": prepared.prepared_sandbox.provider,
            "prepare": prepared.prepared_sandbox.diagnostics,
        }
    if prepared.container_prepare.spec_hash:
        trace["container"] = {
            "spec_hash": prepared.container_prepare.spec_hash,
            "resource_id": prepared.container_prepare.resource_id,
            **dict(prepared.container_prepare.metadata),
        }

    workspace_score_metadata: dict[str, Any] = {}
    if prepared.workspace_session is not None:
        after = snapshot_workspace(prepared.workspace_session.workspace_dir)
        diff = diff_workspace(prepared.workspace_session.before, after)
        workspace_score_metadata = {
            "workspace_dir": prepared.workspace_session.workspace_dir,
            "workspace_before": dict(prepared.workspace_session.before),
            "workspace_after": after,
            "workspace_diff": diff,
        }
        payload["workspace"] = {
            "workspace_dir": prepared.workspace_session.workspace_dir,
            "before_file_count": len(prepared.workspace_session.before),
            "after_file_count": len(after),
            "diff": diff,
        }
        trace["workspace"] = payload["workspace"]
        emit(
            {
                "event": "runtime.workspace.snapshot",
                "phase": "execute",
                "workspace_dir": prepared.workspace_session.workspace_dir,
                "before_file_count": len(prepared.workspace_session.before),
                "after_file_count": len(after),
                "changed": list(diff.get("changed") or []),
                "deleted": list(diff.get("deleted") or []),
            }
        )

    return PartialTrialResult(
        task_result=task_result,
        trace=trace,
        score_context=_score_context_for_prepared(
            prepared,
            extra_sample_metadata=workspace_score_metadata,
        ),
    )


async def score_trial_phase(prepared: PreparedTrial | TrialRequest, partial: PartialTrialResult) -> TrialOutcome:
    """Apply the scorer(s) to a partial trial result and finalize status."""
    request = prepared.request if isinstance(prepared, PreparedTrial) else prepared
    task_result = partial.task_result
    trace = partial.trace
    score_context = partial.score_context
    variant_id = str(getattr(request.agent, "variant_id", "default"))
    emit = _emit_factory(request)

    if isinstance(prepared, PreparedTrial) and prepared.failed_partial is partial:
        return TrialOutcome(task_result=task_result, scores={}, trace=trace)

    # Use scorers list (backward compat: __post_init__ wraps single scorer)
    scorers = request.scorers
    all_scores: dict[str, Any] = {}
    scorer_error: Exception | None = None

    for scorer in scorers:
        scorer_id = getattr(scorer, "scorer_id", "scorer")
        try:
            emit(
                {
                    "event": "runtime.scorer.start",
                    "phase": "scorer",
                    "task_id": task_result.task_id,
                    "agent_id": task_result.agent_id,
                    "variant_id": variant_id,
                    "sample_id": task_result.sample_id,
                    "scorer_id": scorer_id,
                }
            )
            if hasattr(scorer, "ascore") and callable(scorer.ascore):
                scores = await scorer.ascore(task_result, trace, score_context)
            else:
                scores = await asyncio.to_thread(scorer.score, task_result, trace, score_context)
            validate_scores(scores)
            all_scores.update(scores)
            emit(
                {
                    "event": "runtime.scorer.finish",
                    "phase": "scorer",
                    "task_id": task_result.task_id,
                    "agent_id": task_result.agent_id,
                    "variant_id": variant_id,
                    "sample_id": task_result.sample_id,
                    "scorer_id": scorer_id,
                    "metrics": {k: float(v.value) for k, v in scores.items()},
                    "explanations": [
                        {
                            "metric": e.metric,
                            "value": e.value,
                            "evidence": list(e.evidence),
                            "reason": e.reason,
                            "raw": dict(e.raw),
                        }
                        for e in build_score_explanations(
                            scores,
                            trace=trace,
                            task_result={"status": task_result.status.value},
                        )
                    ],
                }
            )
        except Exception as exc:  # pragma: no cover - defensive catch
            scorer_error = exc
            emit(
                {
                    "event": "runtime.trial.error",
                    "phase": "score",
                    "code": "scorer_error",
                    "message": str(exc),
                    "task_id": task_result.task_id,
                    "agent_id": task_result.agent_id,
                    "variant_id": variant_id,
                    "sample_id": task_result.sample_id,
                    "scorer_id": scorer_id,
                }
            )
            # If only one scorer and it failed, treat as error; otherwise continue
            if len(scorers) == 1:
                task_result = TaskResult(
                    task_id=task_result.task_id,
                    agent_id=task_result.agent_id,
                    sample_id=task_result.sample_id,
                    seed=task_result.seed,
                    status=TaskStatus.ERROR,
                    final_output=task_result.final_output,
                    timing=task_result.timing,
                    usage=task_result.usage,
                    error=ErrorInfo(code="scorer_error", message=str(exc), retryable=False),
                    artifacts=task_result.artifacts,
                    payload=task_result.payload,
                )
                return TrialOutcome(task_result=task_result, scores={}, trace=trace)

    accuracy = all_scores.get("accuracy")
    if (
        task_result.status == TaskStatus.SUCCESS
        and accuracy is not None
        and float(getattr(accuracy, "value", 1.0)) < 1.0
    ):
        task_result = TaskResult(
            task_id=task_result.task_id,
            agent_id=task_result.agent_id,
            sample_id=task_result.sample_id,
            seed=task_result.seed,
            status=TaskStatus.INCORRECT,
            final_output=task_result.final_output,
            timing=task_result.timing,
            usage=task_result.usage,
            error=task_result.error,
            artifacts=task_result.artifacts,
            payload=task_result.payload,
        )
    emit(
        {
            "event": "runtime.trial.finish",
            "phase": "score",
            "task_id": task_result.task_id,
            "agent_id": task_result.agent_id,
            "variant_id": variant_id,
            "sample_id": task_result.sample_id,
            "status": task_result.status.value,
            "message": str((task_result.final_output or {}).get("content") or "")[:240],
            "payload": {
                "final_output": _json_safe(task_result.final_output),
                "scores": {k: float(v.value) for k, v in all_scores.items()},
            },
        }
    )

    return TrialOutcome(task_result=task_result, scores=all_scores, trace=trace)


async def finalize_trial_phase(
    prepared: PreparedTrial | TrialRequest,
    outcome: TrialOutcome,
) -> tuple[TrialOutcome, FinalizedTrialArtifacts]:
    """Persist teardown diagnostics and release resources."""
    if isinstance(prepared, TrialRequest):
        prepared = await prepare_trial_phase(prepared)

    request = prepared.request
    emit = _emit_factory(request)
    teardown_diag: dict[str, Any] | None = None
    container_close: dict[str, Any] | None = None
    finalize_error: Exception | None = None

    emit(
        {
            "event": "runtime.finalize.start",
            "phase": "finalize",
            "task_id": outcome.task_result.task_id,
            "agent_id": outcome.task_result.agent_id,
            "variant_id": prepared.variant_id,
            "sample_id": prepared.sample_id,
        }
    )

    try:
        if prepared.prepared_sandbox is not None:
            emit({"event": "runtime.sandbox.teardown.start", "phase": "finalize", "sandbox_id": prepared.prepared_sandbox.sandbox_id})
            teardown_diag = await prepared.sandbox_runtime.teardown(prepared.prepared_sandbox)
            emit({"event": "runtime.sandbox.teardown.done", "phase": "finalize", "sandbox_id": prepared.prepared_sandbox.sandbox_id})
    except Exception as exc:
        finalize_error = exc
        emit(
            {
                "event": "runtime.trial.error",
                "phase": "finalize",
                "code": "sandbox_teardown_error",
                "message": str(exc),
                "task_id": outcome.task_result.task_id,
                "agent_id": outcome.task_result.agent_id,
                "variant_id": prepared.variant_id,
                "sample_id": prepared.sample_id,
            }
        )

    try:
        close_out = await prepared.container_runtime.finalize_phase(
            outcome_status=outcome.task_result.status.value,
        )
        if close_out is not None:
            container_close = dict(close_out)
    except Exception as exc:
        finalize_error = finalize_error or exc
        emit(
            {
                "event": "runtime.trial.error",
                "phase": "finalize",
                "code": "container_teardown_error",
                "message": str(exc),
                "task_id": outcome.task_result.task_id,
                "agent_id": outcome.task_result.agent_id,
                "variant_id": prepared.variant_id,
                "sample_id": prepared.sample_id,
            }
        )
    finally:
        if prepared.original_max_steps is not None:
            try:
                setattr(request.agent, "max_steps", prepared.original_max_steps)
            except Exception:
                pass

    task_result = outcome.task_result
    trace = dict(outcome.trace)
    payload = dict(task_result.payload)
    if prepared.prepared_sandbox is not None:
        payload["sandbox"] = {
            "sandbox_id": prepared.prepared_sandbox.sandbox_id,
            "spec_hash": prepared.prepared_sandbox.spec_hash,
            "provider": prepared.prepared_sandbox.provider,
            "prepare": prepared.prepared_sandbox.diagnostics,
            "teardown": teardown_diag or {},
        }
        trace["sandbox"] = {
            "sandbox_id": prepared.prepared_sandbox.sandbox_id,
            "spec_hash": prepared.prepared_sandbox.spec_hash,
            "provider": prepared.prepared_sandbox.provider,
            "prepare": prepared.prepared_sandbox.diagnostics,
            "teardown": teardown_diag or {},
        }
    if container_close is not None:
        payload["container_finalize"] = dict(container_close)
        trace["container_finalize"] = dict(container_close)
    if prepared.workspace_session is not None:
        after = snapshot_workspace(prepared.workspace_session.workspace_dir)
        diff = diff_workspace(prepared.workspace_session.before, after)
        payload["workspace"] = {
            "workspace_dir": prepared.workspace_session.workspace_dir,
            "before_file_count": len(prepared.workspace_session.before),
            "after_file_count": len(after),
            "diff": diff,
        }
        trace["workspace"] = payload["workspace"]

    if finalize_error is not None:
        task_result = TaskResult(
            task_id=task_result.task_id,
            agent_id=task_result.agent_id,
            sample_id=task_result.sample_id,
            seed=task_result.seed,
            status=TaskStatus.ERROR,
            final_output=task_result.final_output,
            timing=task_result.timing,
            usage=task_result.usage,
            error=ErrorInfo(code="finalize_error", message=str(finalize_error), retryable=False),
            artifacts=task_result.artifacts,
            payload=payload,
        )
        outcome = TrialOutcome(task_result=task_result, scores=outcome.scores, trace=trace)
    elif payload != task_result.payload or trace != outcome.trace:
        task_result = TaskResult(
            task_id=task_result.task_id,
            agent_id=task_result.agent_id,
            sample_id=task_result.sample_id,
            seed=task_result.seed,
            status=task_result.status,
            final_output=task_result.final_output,
            timing=task_result.timing,
            usage=task_result.usage,
            error=task_result.error,
            artifacts=task_result.artifacts,
            payload=payload,
        )
        outcome = TrialOutcome(task_result=task_result, scores=outcome.scores, trace=trace)

    emit(
        {
            "event": "runtime.finalize.finish",
            "phase": "finalize",
            "task_id": outcome.task_result.task_id,
            "agent_id": outcome.task_result.agent_id,
            "variant_id": prepared.variant_id,
            "sample_id": prepared.sample_id,
            "status": outcome.task_result.status.value,
        }
    )

    return outcome, FinalizedTrialArtifacts(teardown=teardown_diag, container_close=container_close)


async def execute_trial(request: TrialRequest) -> TrialOutcome:
    """Execute one full trial for callers that still expect the old API."""

    prepared = await prepare_trial_phase(request)
    partial = await execute_agent_phase(prepared)
    outcome = await score_trial_phase(prepared, partial)
    finalized, _ = await finalize_trial_phase(prepared, outcome)
    return finalized
