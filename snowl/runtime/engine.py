"""Trial execution engine for Task x AgentVariant x Sample."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from snowl.core.agent import Agent, AgentContext, AgentState, StopReason, validate_agent
from snowl.core.env import ensure_tool_ops_compatible, validate_env_spec
from snowl.core.scorer import ScoreContext, Scorer, validate_scorer, validate_scores
from snowl.core.task import Task, validate_task
from snowl.core.task_result import ErrorInfo, TaskResult, TaskStatus, Timing, Usage
from snowl.core.tool import ToolSpec, resolve_tool_spec
from snowl.envs.sandbox_runtime import SandboxRuntime, WarmPoolSandboxRuntime
from snowl.errors import SnowlValidationError
from snowl.runtime.container_runtime import ContainerRuntime
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
    scorer: Scorer
    sample: Mapping[str, Any]
    seed: int | None = None
    tools: Sequence[Any] | None = None
    sandbox_runtime: SandboxRuntime | None = None
    limits: TrialLimits = TrialLimits()
    on_event: Callable[[dict[str, Any]], None] | None = None


@dataclass(frozen=True)
class TrialOutcome:
    task_result: TaskResult
    scores: dict[str, Any]
    trace: dict[str, Any]


def _initial_messages(sample: Mapping[str, Any]) -> list[dict[str, Any]]:
    if "messages" in sample and isinstance(sample["messages"], list):
        return [dict(message) for message in sample["messages"]]

    if "input" in sample:
        return [{"role": "user", "content": str(sample["input"])}]

    raise SnowlValidationError("Sample must contain either 'messages' or 'input'.")


def _status_from_stop_reason(stop_reason: StopReason | None) -> TaskStatus:
    if stop_reason == StopReason.CANCELLED:
        return TaskStatus.CANCELLED

    if stop_reason in {StopReason.MAX_STEPS, StopReason.LIMIT_EXCEEDED}:
        return TaskStatus.LIMIT_EXCEEDED

    if stop_reason == StopReason.ERROR:
        return TaskStatus.ERROR

    return TaskStatus.SUCCESS


async def execute_trial(request: TrialRequest) -> TrialOutcome:
    """Execute one trial and produce TaskResult + scores + trace."""

    validate_task(request.task)
    validate_env_spec(request.task.env_spec)
    validate_agent(request.agent)
    validate_scorer(request.scorer)

    started = int(time.time() * 1000)
    sample_id = str(request.sample.get("id")) if request.sample.get("id") is not None else None
    variant_id = str(getattr(request.agent, "variant_id", "default"))
    variant_model = getattr(request.agent, "model", None)

    def _emit(event: dict[str, Any]) -> None:
        if request.on_event is None:
            return
        try:
            request.on_event(dict(event))
        except Exception:
            return

    _emit(
        {
            "event": "runtime.trial.start",
            "phase": "agent",
            "task_id": request.task.task_id,
            "agent_id": getattr(request.agent, "agent_id"),
            "variant_id": variant_id,
            "sample_id": sample_id,
        }
    )

    state = AgentState(messages=_initial_messages(request.sample))
    context = AgentContext(
        task_id=request.task.task_id,
        sample_id=sample_id,
        metadata={
            "sample": dict(request.sample),
            "task_metadata": request.task.metadata,
            "__snowl_emit_event": _emit,
        },
    )
    container_runtime = ContainerRuntime(
        task_id=request.task.task_id,
        agent_id=getattr(request.agent, "agent_id"),
        variant_id=variant_id,
        task_env_type=request.task.env_spec.env_type,
        task_metadata=request.task.metadata,
        sample=request.sample,
        emit=_emit,
    )
    container_session = None
    try:
        container_session = container_runtime.prepare()
        if container_session is not None:
            context.metadata["__snowl_container_session"] = container_session
    except Exception as exc:
        ended = int(time.time() * 1000)
        error = ErrorInfo(code="container_runtime_error", message=str(exc), retryable=False)
        task_result = TaskResult(
            task_id=request.task.task_id,
            agent_id=getattr(request.agent, "agent_id"),
            sample_id=sample_id,
            seed=request.seed,
            status=TaskStatus.ERROR,
            final_output={},
            timing=Timing(started_at_ms=started, ended_at_ms=ended, duration_ms=max(0, ended - started)),
            usage=Usage(),
            error=error,
            payload={
                "stop_reason": StopReason.ERROR.value,
                "phase": "container_prepare",
                "variant_id": variant_id,
                "model": variant_model,
            },
        )
        trace = {
            "trace_events": [{"event": "runtime.container.error", "message": str(exc)}],
            "actions": [],
            "observations": [],
            "stop_reason": StopReason.ERROR.value,
        }
        _emit(
            {
                "event": "runtime.trial.error",
                "phase": "error",
                "code": error.code,
                "message": error.message,
                "task_id": request.task.task_id,
                "agent_id": getattr(request.agent, "agent_id"),
                "variant_id": variant_id,
                "sample_id": sample_id,
            }
        )
        return TrialOutcome(task_result=task_result, scores={}, trace=trace)
    resolved_tool_specs: list[ToolSpec] = []
    if request.tools:
        resolved_tool_specs = [resolve_tool_spec(t) for t in request.tools]

    required_ops = {op for spec in resolved_tool_specs for op in spec.required_ops}
    provided_ops = set(request.task.env_spec.provided_ops)
    missing_ops = ensure_tool_ops_compatible(required_ops, provided_ops)
    if missing_ops:
        ended = int(time.time() * 1000)
        error = ErrorInfo(
            code="env_ops_mismatch",
            message=(
                "Tool requires unsupported env ops: "
                + ", ".join(sorted(missing_ops))
                + f". Env provides: {', '.join(sorted(provided_ops)) or '(none)'}."
            ),
            retryable=False,
            details={
                "missing_ops": sorted(missing_ops),
                "provided_ops": sorted(provided_ops),
                "required_ops": sorted(required_ops),
                "variant_id": variant_id,
            },
        )
        task_result = TaskResult(
            task_id=request.task.task_id,
            agent_id=getattr(request.agent, "agent_id"),
            sample_id=sample_id,
            seed=request.seed,
            status=TaskStatus.ERROR,
            final_output={},
            timing=Timing(started_at_ms=started, ended_at_ms=ended, duration_ms=max(0, ended - started)),
            usage=Usage(),
            error=error,
            payload={
                "stop_reason": StopReason.ERROR.value,
                "phase": "preflight_validation",
                "variant_id": variant_id,
                "model": variant_model,
            },
        )
        trace = {
            "trace_events": [
                {
                    "event": "runtime.validation_error",
                    "code": "env_ops_mismatch",
                    "missing_ops": sorted(missing_ops),
                }
            ],
            "actions": [],
            "observations": [],
            "stop_reason": StopReason.ERROR.value,
        }
        _emit(
            {
                "event": "runtime.trial.error",
                "phase": "error",
                "code": error.code,
                "message": error.message,
                "task_id": request.task.task_id,
                "agent_id": getattr(request.agent, "agent_id"),
                "variant_id": variant_id,
                "sample_id": sample_id,
            }
        )
        return TrialOutcome(task_result=task_result, scores={}, trace=trace)

    original_max_steps = None
    if request.limits.max_steps is not None and hasattr(request.agent, "max_steps"):
        try:
            original_max_steps = getattr(request.agent, "max_steps")
            setattr(request.agent, "max_steps", request.limits.max_steps)
        except Exception:
            original_max_steps = None

    error: ErrorInfo | None = None
    status = TaskStatus.SUCCESS
    sandbox_runtime = request.sandbox_runtime or _DEFAULT_SANDBOX_RUNTIME
    prepared_sandbox = None
    teardown_diag: dict[str, Any] | None = None

    try:
        if request.task.env_spec.sandbox_spec is not None:
            _emit({"event": "runtime.sandbox.prepare.start", "provider": request.task.env_spec.sandbox_spec.provider})
            prepared_sandbox = await sandbox_runtime.prepare(request.task.env_spec.sandbox_spec)
            _emit(
                {
                    "event": "runtime.sandbox.prepare.done",
                    "phase": "env",
                    "provider": prepared_sandbox.provider,
                    "sandbox_id": prepared_sandbox.sandbox_id,
                }
            )

        async def _agent_run():
            return await request.agent.run(state, context, tools=resolved_tool_specs)

        if request.limits.time_limit_seconds is not None:
            if prepared_sandbox is not None:
                state = await asyncio.wait_for(
                    sandbox_runtime.run(prepared_sandbox, _agent_run),
                    timeout=request.limits.time_limit_seconds,
                )
            else:
                state = await asyncio.wait_for(
                    _agent_run(),
                    timeout=request.limits.time_limit_seconds,
                )
        else:
            if prepared_sandbox is not None:
                state = await sandbox_runtime.run(prepared_sandbox, _agent_run)
            else:
                state = await _agent_run()

        status = _status_from_stop_reason(state.stop_reason)
    except TimeoutError:
        status = TaskStatus.LIMIT_EXCEEDED
        state.stop_reason = StopReason.LIMIT_EXCEEDED
        error = ErrorInfo(code="time_limit_exceeded", message="Trial exceeded time limit.")
        _emit(
            {
                "event": "runtime.trial.error",
                "phase": "error",
                "code": error.code,
                "message": error.message,
                "task_id": request.task.task_id,
                "agent_id": getattr(request.agent, "agent_id"),
                "variant_id": variant_id,
                "sample_id": sample_id,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive catch
        status = TaskStatus.ERROR
        state.stop_reason = StopReason.ERROR
        error = ErrorInfo(code="agent_runtime_error", message=str(exc), retryable=False)
        _emit(
            {
                "event": "runtime.trial.error",
                "phase": "error",
                "code": error.code,
                "message": error.message,
                "task_id": request.task.task_id,
                "agent_id": getattr(request.agent, "agent_id"),
                "variant_id": variant_id,
                "sample_id": sample_id,
            }
        )
    finally:
        try:
            container_runtime.close()
        except Exception as exc:
            _emit(
                {
                    "event": "runtime.container.teardown.error",
                    "phase": "env",
                    "task_id": request.task.task_id,
                    "agent_id": getattr(request.agent, "agent_id"),
                    "variant_id": variant_id,
                    "sample_id": sample_id,
                    "message": str(exc),
                }
            )
        if prepared_sandbox is not None:
            _emit({"event": "runtime.sandbox.teardown.start", "sandbox_id": prepared_sandbox.sandbox_id})
            teardown_diag = await sandbox_runtime.teardown(prepared_sandbox)
            _emit({"event": "runtime.sandbox.teardown.done", "sandbox_id": prepared_sandbox.sandbox_id})
        if original_max_steps is not None:
            try:
                setattr(request.agent, "max_steps", original_max_steps)
            except Exception:
                pass

    output = state.output or {}
    usage_data = output.get("usage") or {}
    usage = Usage(
        input_tokens=int(usage_data.get("input_tokens", 0) or 0),
        output_tokens=int(usage_data.get("output_tokens", 0) or 0),
        total_tokens=int(usage_data.get("total_tokens", 0) or 0),
        estimated_cost_usd=None,
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
        _emit(
            {
                "event": "runtime.trial.error",
                "phase": "error",
                "code": error.code,
                "message": error.message,
                "task_id": request.task.task_id,
                "agent_id": getattr(request.agent, "agent_id"),
                "variant_id": variant_id,
                "sample_id": sample_id,
            }
        )

    ended = int(time.time() * 1000)
    task_result = TaskResult(
        task_id=request.task.task_id,
        agent_id=getattr(request.agent, "agent_id"),
        sample_id=sample_id,
        seed=request.seed,
        status=status,
        final_output={
            "message": output.get("message", {}),
            "content": (output.get("message", {}) or {}).get("content"),
            **({"traj": output.get("traj")} if output.get("traj") is not None else {}),
        },
        timing=Timing(
            started_at_ms=started,
            ended_at_ms=ended,
            duration_ms=max(0, ended - started),
        ),
        usage=usage,
        error=error,
        payload={
            "stop_reason": state.stop_reason.value if state.stop_reason else None,
            "variant_id": variant_id,
            "model": variant_model,
            **(
                {"osworld_score": output.get("osworld_score")}
                if output.get("osworld_score") is not None
                else {}
            ),
        },
    )
    if prepared_sandbox is not None:
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
            payload={
                **task_result.payload,
                "sandbox": {
                    "sandbox_id": prepared_sandbox.sandbox_id,
                    "spec_hash": prepared_sandbox.spec_hash,
                    "provider": prepared_sandbox.provider,
                    "teardown": teardown_diag or {},
                },
            },
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
    if prepared_sandbox is not None:
        trace["sandbox"] = {
            "sandbox_id": prepared_sandbox.sandbox_id,
            "spec_hash": prepared_sandbox.spec_hash,
            "provider": prepared_sandbox.provider,
            "prepare": prepared_sandbox.diagnostics,
            "teardown": teardown_diag or {},
        }

    score_context = ScoreContext(
        task_id=request.task.task_id,
        agent_id=getattr(request.agent, "agent_id"),
        sample_id=sample_id,
        task_metadata=request.task.metadata,
        sample_metadata=dict(request.sample.get("metadata", {})),
    )

    try:
        _emit(
            {
                "event": "runtime.scorer.start",
                "phase": "scorer",
                "task_id": task_result.task_id,
                "agent_id": task_result.agent_id,
                "variant_id": variant_id,
                "sample_id": task_result.sample_id,
                "scorer_id": getattr(request.scorer, "scorer_id", "scorer"),
            }
        )
        scores = request.scorer.score(task_result, trace, score_context)
        validate_scores(scores)
        _emit(
            {
                "event": "runtime.scorer.finish",
                "phase": "scorer",
                "task_id": task_result.task_id,
                "agent_id": task_result.agent_id,
                "variant_id": variant_id,
                "sample_id": task_result.sample_id,
                "scorer_id": getattr(request.scorer, "scorer_id", "scorer"),
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
            payload=task_result.payload,
        )
        _emit(
            {
                "event": "runtime.trial.error",
                "phase": "error",
                "code": "scorer_error",
                "message": str(exc),
                "task_id": task_result.task_id,
                "agent_id": task_result.agent_id,
                "variant_id": variant_id,
                "sample_id": task_result.sample_id,
            }
        )
        return TrialOutcome(task_result=task_result, scores={}, trace=trace)

    # status transition with scorer signal:
    # if an "accuracy" metric exists and is < 1.0, mark incorrect unless already terminal error/limit.
    accuracy = scores.get("accuracy")
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
            payload=task_result.payload,
        )
    _emit(
        {
            "event": "runtime.trial.finish",
            "phase": "task",
            "task_id": task_result.task_id,
            "agent_id": task_result.agent_id,
            "variant_id": variant_id,
            "sample_id": task_result.sample_id,
            "status": task_result.status.value,
        }
    )

    return TrialOutcome(task_result=task_result, scores=scores, trace=trace)
