"""Finalize phase for single-trial execution.

Hosts ``finalize_trial_phase``.
"""

from __future__ import annotations

from typing import Any

from snowl.core.task_result import ErrorInfo, TaskResult, TaskStatus
from snowl.runtime.workspace import diff_workspace, snapshot_workspace

from ._shared import (
    FinalizedTrialArtifacts,
    PreparedTrial,
    TrialOutcome,
    TrialRequest,
    _emit_factory,
)
from .prepare import prepare_trial_phase


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
        if prepared.mcp_manager is not None:
            emit({"event": "runtime.mcp.stop", "phase": "finalize"})
            await prepared.mcp_manager.stop_all()
            emit({"event": "runtime.mcp.stopped", "phase": "finalize"})
    except Exception as exc:
        finalize_error = exc
        emit({
            "event": "runtime.mcp.error",
            "phase": "finalize",
            "message": str(exc),
        })

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
