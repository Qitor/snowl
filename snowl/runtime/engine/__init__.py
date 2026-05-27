"""Engine package — execution-plane implementation for single-trial phases.

Re-exports all public symbols from the sub-modules and defines ``execute_trial``
as a convenience wrapper for the full prepare -> execute -> score -> finalize
pipeline.
"""

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

from ._shared import (
    FinalizedTrialArtifacts,
    PartialTrialResult,
    PreparedTrial,
    TrialLimits,
    TrialOutcome,
    TrialRequest,
    _DEFAULT_SANDBOX_RUNTIME,
    _benchmark_has_canary,
    _build_dynamic_tool_specs,
    _build_score_context,
    _emit_factory,
    _error_partial,
    _extract_sample_input,
    _get_extra_payload_keys,
    _initial_messages,
    _json_safe,
    _merge_project_and_dynamic_tools,
    _sample_declared_tool_names,
    _sample_declared_tool_schemas,
    _sample_preview_text,
    _score_context_for_prepared,
    _select_sample_tools,
    _status_from_stop_reason,
)
from .prepare import prepare_trial_phase
from .execute import execute_agent_phase
from .score import score_trial_phase
from .finalize import finalize_trial_phase


async def execute_trial(request: TrialRequest) -> TrialOutcome:
    """Execute one full trial for callers that still expect the old API."""

    prepared = await prepare_trial_phase(request)
    partial = await execute_agent_phase(prepared)
    outcome = await score_trial_phase(prepared, partial)
    finalized, _ = await finalize_trial_phase(prepared, outcome)
    return finalized


__all__ = [
    # Public data classes
    "TrialLimits",
    "TrialRequest",
    "TrialOutcome",
    "PartialTrialResult",
    "PreparedTrial",
    "FinalizedTrialArtifacts",
    # Public phase functions
    "prepare_trial_phase",
    "execute_agent_phase",
    "score_trial_phase",
    "finalize_trial_phase",
    # Convenience wrapper
    "execute_trial",
    # Re-exported types (were importable from old monolithic engine.py)
    "Agent",
    "AgentContext",
    "AgentState",
    "ArtifactRef",
    "ContainerPrepareResult",
    "ContainerRuntime",
    "ErrorInfo",
    "RuntimeContainerLifecycleManager",
    "RuntimeWorkspaceManager",
    "RuntimeWorkspaceSession",
    "SandboxRuntime",
    "ScoreContext",
    "Scorer",
    "StopReason",
    "Task",
    "TaskExecutionPlan",
    "TaskResult",
    "TaskStatus",
    "Timing",
    "ToolSpec",
    "TrialDescriptor",
    "Usage",
    "WarmPoolSandboxRuntime",
    "build_score_explanations",
    "diff_workspace",
    "ensure_tool_ops_compatible",
    "resolve_runtime_container_spec",
    "resolve_tool_spec",
    "resolve_workspace_spec",
    "snapshot_workspace",
    "validate_agent",
    "validate_env_spec",
    "validate_scores",
    "validate_scorer",
    "validate_task",
    # Private helpers (used by tests and other runtime modules)
    "_DEFAULT_SANDBOX_RUNTIME",
    "_benchmark_has_canary",
    "_build_dynamic_tool_specs",
    "_build_score_context",
    "_emit_factory",
    "_error_partial",
    "_extract_sample_input",
    "_get_extra_payload_keys",
    "_initial_messages",
    "_json_safe",
    "_merge_project_and_dynamic_tools",
    "_sample_declared_tool_names",
    "_sample_declared_tool_schemas",
    "_sample_preview_text",
    "_score_context_for_prepared",
    "_select_sample_tools",
    "_status_from_stop_reason",
]
