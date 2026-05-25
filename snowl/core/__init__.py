"""Core contract package facade for tasks, agents, tools, scorers, env specs, and results.

Framework role:
- Re-exports typed contracts and validators that define Snowl's authoring/runtime boundary.

Runtime/usage wiring:
- Imported by nearly every subsystem; this module is the canonical contract entrypoint.

Change guardrails:
- Maintain backward-compatible exports when possible; contract churn here propagates repo-wide.
"""

from snowl.core.agent import (
    Action,
    Agent,
    AgentContext,
    AgentState,
    Observation,
    StopReason,
    agent,
    validate_agent,
)
from snowl.core.agent_variant import (
    AgentVariant,
    AgentVariantAdapter,
    bind_agent_variant,
    make_agent_variant,
    validate_agent_variant,
)
from snowl.core.env import (
    EnvSpec,
    FileOps,
    ProcessOps,
    SandboxSpec,
    VerifierMode,
    VerifierSpec,
    WebOps,
    ensure_tool_ops_compatible,
    validate_env_spec,
    validate_verifier_spec,
)
from snowl.core.scorer import (
    AsyncScorer,
    Score,
    ScoreContext,
    Scorer,
    SyncScorerAdapter,
    get_scorer_metrics,
    is_async_scorer,
    scorer,
    validate_async_scorer,
    validate_scorer,
    validate_scores,
)
from snowl.core.task import (
    Task,
    TaskProvider,
    task,
    validate_task,
    validate_task_provider,
)
from snowl.core.task_result import (
    ArtifactRef,
    ErrorInfo,
    StepResult,
    TaskResult,
    TaskStatus,
    Timing,
    Usage,
    validate_task_result,
)
from snowl.core.hooks import (
    HooksBridge,
    RunContext,
    TrialContext,
    TrialHooks,
    hooks,
)
from snowl.core.hooks_builtin import (
    AuditLogHook,
    CostTrackerHook,
    ProgressHook,
    RateLimitAlertHook,
)
from snowl.core.sample import (
    Sample,
)
from snowl.core.solver import (
    AgentSolver,
    Chain,
    Fork,
    Generate,
    Solver,
    chain,
    fork,
    solver,
)
from snowl.core.step import (
    TaskStep,
)
from snowl.core.mcp import (
    MCPServerSpec,
    mcp_server_spec_from_dict,
    validate_mcp_server_spec,
)
from snowl.core.reducer import (
    MaxReducer,
    MeanReducer,
    PassAtKReducer,
    ScoreReducer,
    resolve_score_reducer,
    validate_score_reducer,
)
from snowl.core.tool import (
    ToolRegistry,
    ToolSpec,
    build_tool_spec,
    get_default_tool_registry,
    resolve_tool_spec,
    tool,
)

__all__ = [
    "Action",
    "Agent",
    "AgentContext",
    "AgentSolver",
    "AgentState",
    "AgentVariant",
    "AgentVariantAdapter",
    "AsyncScorer",
    "ArtifactRef",
    "AuditLogHook",
    "CostTrackerHook",
    "Chain",
    "Fork",
    "EnvSpec",
    "MCPServerSpec",
    "MaxReducer",
    "MeanReducer",
    "PassAtKReducer",
    "ErrorInfo",
    "FileOps",
    "Generate",
    "get_scorer_metrics",
    "HooksBridge",
    "RunContext",
    "Observation",
    "ProcessOps",
    "ProgressHook",
    "RateLimitAlertHook",
    "SandboxSpec",
    "Sample",
    "Score",
    "ScoreContext",
    "ScoreReducer",
    "Scorer",
    "solver",
    "Solver",
    "StepResult",
    "StopReason",
    "SyncScorerAdapter",
    "Task",
    "TaskProvider",
    "TaskResult",
    "TaskStep",
    "TaskStatus",
    "Timing",
    "VerifierMode",
    "VerifierSpec",
    "TrialContext",
    "TrialHooks",
    "ToolRegistry",
    "ToolSpec",
    "Usage",
    "WebOps",
    "ensure_tool_ops_compatible",
    "fork",
    "is_async_scorer",
    "validate_agent",
    "validate_agent_variant",
    "validate_async_scorer",
    "validate_env_spec",
    "validate_mcp_server_spec",
    "validate_verifier_spec",
    "build_tool_spec",
    "chain",
    "bind_agent_variant",
    "get_default_tool_registry",
    "make_agent_variant",
    "resolve_tool_spec",
    "tool",
    "task",
    "agent",
    "hooks",
    "mcp_server_spec_from_dict",
    "scorer",
    "validate_scorer",
    "validate_scores",
    "validate_task",
    "validate_task_provider",
    "validate_task_result",
    "resolve_score_reducer",
    "validate_score_reducer",
]
