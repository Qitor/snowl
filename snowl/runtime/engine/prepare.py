"""Prepare phase for single-trial execution.

Hosts ``prepare_trial_phase`` and the MCP spec collector ``_collect_mcp_specs``.
"""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence

from snowl.core.agent import AgentContext, AgentState, validate_agent
from snowl.core.env import ensure_tool_ops_compatible, validate_env_spec
from snowl.core.scorer import validate_scorer
from snowl.core.task import validate_task
from snowl.core.tool import ToolSpec, resolve_tool_spec
from snowl.runtime.container_contract import resolve_runtime_container_spec
from snowl.runtime.container_runtime import ContainerPrepareResult, ContainerRuntime
from snowl.runtime.workspace import (
    RuntimeWorkspaceManager,
    RuntimeWorkspaceSession,
    resolve_workspace_spec,
)

from ._shared import (
    _DEFAULT_SANDBOX_RUNTIME,
    PreparedTrial,
    TrialRequest,
    _benchmark_has_canary,
    _build_dynamic_tool_specs,
    _emit_factory,
    _error_partial,
    _extract_sample_input,
    _initial_messages,
    _merge_project_and_dynamic_tools,
    _sample_preview_text,
    _select_sample_tools,
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

    # Auto-strip canary markers if the benchmark declares has_canary
    if _benchmark_has_canary(request.task):
        from snowl.canary import strip_canary_from_sample
        sample_for_runtime = strip_canary_from_sample(sample_for_runtime)

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

    # -- MCP server startup and tool discovery --
    mcp_manager = None
    mcp_specs = _collect_mcp_specs(request, state)
    if mcp_specs:
        from snowl.runtime.mcp_manager import MCPServerManager
        from snowl.tools.mcp_adapter import discover_mcp_tool_specs
        try:
            mcp_manager = MCPServerManager(mcp_specs)
            await mcp_manager.start_all()
            mcp_tool_specs = await discover_mcp_tool_specs(mcp_manager)
            resolved_tool_specs = list(resolved_tool_specs)
            existing_names = {s.name for s in resolved_tool_specs}
            for spec in mcp_tool_specs:
                if spec.name not in existing_names:
                    resolved_tool_specs.append(spec)
                    existing_names.add(spec.name)
            context.metadata["available_tool_names"] = [s.name for s in resolved_tool_specs]
            emit({
                "event": "runtime.mcp.started",
                "phase": "prepare",
                "servers": mcp_manager.active_server_names,
                "tools_discovered": len(mcp_tool_specs),
            })
        except Exception as exc:
            if mcp_manager is not None:
                try:
                    await mcp_manager.stop_all()
                except Exception:
                    pass
                mcp_manager = None
            emit({
                "event": "runtime.mcp.error",
                "phase": "prepare",
                "message": str(exc),
            })

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
        mcp_manager=mcp_manager,
    )


def _collect_mcp_specs(request: TrialRequest, state: AgentState) -> tuple[Any, ...]:
    """Collect MCP server specs from all sources: EnvSpec, solver chain, and request."""
    from snowl.core.mcp import MCPServerSpec, mcp_server_spec_from_dict

    specs: list[MCPServerSpec] = []

    # 1. From task.env_spec.mcp_servers
    for spec in request.task.env_spec.mcp_servers:
        specs.append(spec)

    # 2. From solver chain state (use_tools().with_mcp_servers())
    solver_mcp = (state.output or {}).get("_solver_mcp_servers", [])
    for s in solver_mcp:
        if isinstance(s, MCPServerSpec):
            specs.append(s)
        elif isinstance(s, dict):
            try:
                specs.append(mcp_server_spec_from_dict(s))
            except Exception:
                pass

    # 3. From project config (stored on TrialRequest via project_config)
    config_mcp = getattr(request, "mcp_servers", None)
    if config_mcp and isinstance(config_mcp, list):
        for s in config_mcp:
            if isinstance(s, MCPServerSpec):
                specs.append(s)
            elif isinstance(s, dict):
                try:
                    specs.append(mcp_server_spec_from_dict(s))
                except Exception:
                    pass

    # Deduplicate by name
    seen: set[str] = set()
    unique: list[MCPServerSpec] = []
    for spec in specs:
        if spec.name not in seen:
            seen.add(spec.name)
            unique.append(spec)

    return tuple(unique)
