"""Execute phase for single-trial execution.

Hosts ``execute_agent_phase`` and ``_inject_execution_middleware``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Mapping

from snowl.core.agent import StopReason
from snowl.core.task_result import ArtifactRef, ErrorInfo, TaskResult, TaskStatus, Timing, Usage
from snowl.runtime.workspace import diff_workspace, snapshot_workspace

from ._shared import (
    PartialTrialResult,
    PreparedTrial,
    TrialRequest,
    _emit_factory,
    _extract_sample_input,
    _get_extra_payload_keys,
    _score_context_for_prepared,
    _status_from_stop_reason,
)
from .prepare import prepare_trial_phase


def _inject_execution_middleware(prepared: PreparedTrial, mode: str, config: dict[str, Any]) -> None:
    """Inject middleware chain based on execution_mode before agent.run()."""
    agent = prepared.request.agent
    if mode == "emulated":
        from snowl.tools.emulated_tool import EmulatedToolWrapper
        from snowl.tools.middleware import MiddlewareChain
        from snowl.model import OpenAICompatibleChatClient
        from snowl.model.openai_compatible import OpenAICompatibleConfig
        emulator_model = config.get("emulator_model", "gpt-4o-mini")
        # Build emulator client from provider config if available
        emulator_config = OpenAICompatibleConfig(
            base_url=config.get("emulator_base_url", ""),
            api_key=config.get("emulator_api_key", ""),
            model=emulator_model,
        )
        emulator_client = OpenAICompatibleChatClient(emulator_config)
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

    # Multi-step task: delegate to MultiStepExecutor if task has steps
    step_results: list[Any] = []
    if request.task.steps:
        from snowl.runtime.multi_step import MultiStepExecutor
        executor = MultiStepExecutor()
        try:
            step_results = await executor.execute(
                task=request.task,
                agent=request.agent,
                sample=dict(prepared.sample),
                context=prepared.context,
                tools=prepared.resolved_tool_specs,
            )
            # Compute aggregate status from step results
            if any(sr.status == TaskStatus.ERROR for sr in step_results):
                status = TaskStatus.ERROR
            elif any(sr.status == TaskStatus.LIMIT_EXCEEDED for sr in step_results):
                status = TaskStatus.LIMIT_EXCEEDED
            else:
                status = TaskStatus.SUCCESS
            # The executor mutates state in-place via agent.run()
        except Exception as exc:
            status = TaskStatus.ERROR
            state.stop_reason = StopReason.ERROR
            error = ErrorInfo(code="multi_step_error", message=str(exc), retryable=False)
        # Fall through to the normal result construction below,
        # which will use the current state, status, and error.
        # step_results will be attached to TaskResult later.

    # Apply execution strategy: inject middleware based on execution_mode
    execution_mode = request.execution_mode or "native"

    # Detect solver chain execution path
    solver_chain = request.solver_chain
    if solver_chain is None:
        solver_chain = getattr(request.agent, "solver_chain", None)

    if solver_chain is not None:
        # Solver chain execution: inject context + tools into named attributes
        prepared.state.solver_context = prepared.context
        existing_tools = list(prepared.state.solver_tools or [])
        for spec in prepared.resolved_tool_specs:
            if spec.name not in {t.name for t in existing_tools}:
                existing_tools.append(spec)
        prepared.state.solver_tools = existing_tools
        if request.middleware_config:
            existing_mw = list(prepared.state.solver_middleware or [])
            prepared.state.solver_middleware = existing_mw

    # Default no-op generate for solver chains (replaced by bridge if active)
    async def _noop_generate(**kwargs):
        raise RuntimeError(
            "No framework generate() available; "
            "include generate(model_client) in your solver chain "
            "or enable bridge mode in project.yml."
        )

    try:
        if solver_chain is not None:
            # Solver chain path
            async def _solver_run():
                # Check if bridge mode is active and provide a real generate fn
                generate_fn = _noop_generate
                try:
                    from snowl.bridges._config import get_bridge_config
                    bc = get_bridge_config()
                    if bc is not None and bc.enabled and bc.model_client is not None:
                        from snowl.bridges._generate import bridge_generate
                        generate_fn = bridge_generate(bc.model_client)
                except ImportError:
                    pass
                return await solver_chain(prepared.state, generate_fn)

            _run_fn = _solver_run
        else:
            # Traditional agent.run() path
            # Check if bridge mode should wrap agent execution
            bridge_enabled = False
            bridge_model_client = None
            try:
                from snowl.bridges._config import get_bridge_config
                bc = get_bridge_config()
                if bc is not None and bc.enabled and bc.model_client is not None:
                    bridge_enabled = True
                    bridge_model_client = bc.model_client
            except ImportError:
                pass

            if bridge_enabled and bridge_model_client is not None:
                if execution_mode != "native":
                    _inject_execution_middleware(prepared, execution_mode, request.middleware_config)

                async def _agent_run():
                    from snowl.bridges import snowl_bridge
                    async with snowl_bridge(model_client=bridge_model_client) as handle:
                        state = await request.agent.run(prepared.state, prepared.context, tools=prepared.resolved_tool_specs)
                        # Merge bridge usage into state output
                        if state.output is None:
                            state.output = {}
                        bridge_usage = handle.usage()
                        existing_usage = state.output.get("usage") or {}
                        state.output["usage"] = {
                            "input_tokens": existing_usage.get("input_tokens", 0) + bridge_usage["input_tokens"],
                            "output_tokens": existing_usage.get("output_tokens", 0) + bridge_usage["output_tokens"],
                            "total_tokens": existing_usage.get("total_tokens", 0) + bridge_usage["total_tokens"],
                        }
                        return state

                _run_fn = _agent_run
            else:
                if execution_mode != "native":
                    _inject_execution_middleware(prepared, execution_mode, request.middleware_config)

                async def _agent_run():
                    return await request.agent.run(prepared.state, prepared.context, tools=prepared.resolved_tool_specs)

                _run_fn = _agent_run

        if request.limits.time_limit_seconds is not None:
            if prepared.prepared_sandbox is not None:
                state = await asyncio.wait_for(
                    prepared.sandbox_runtime.run(prepared.prepared_sandbox, _run_fn),
                    timeout=request.limits.time_limit_seconds,
                )
            else:
                state = await asyncio.wait_for(_run_fn(), timeout=request.limits.time_limit_seconds)
        else:
            if prepared.prepared_sandbox is not None:
                state = await prepared.sandbox_runtime.run(prepared.prepared_sandbox, _run_fn)
            else:
                state = await _run_fn()

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
    for _key in _get_extra_payload_keys(request.task):
        if output.get(_key) is not None:
            payload[_key] = output[_key]
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
        step_results=step_results if request.task.steps else None,
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
    for _key in _get_extra_payload_keys(request.task):
        if output.get(_key) is not None:
            trace[_key] = output[_key]
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
