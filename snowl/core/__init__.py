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
    WebOps,
    ensure_tool_ops_compatible,
    validate_env_spec,
)
from snowl.core.scorer import (
    Score,
    ScoreContext,
    Scorer,
    scorer,
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
    TaskResult,
    TaskStatus,
    Timing,
    Usage,
    validate_task_result,
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
    "AgentState",
    "AgentVariant",
    "AgentVariantAdapter",
    "ArtifactRef",
    "EnvSpec",
    "ErrorInfo",
    "FileOps",
    "Observation",
    "ProcessOps",
    "SandboxSpec",
    "Score",
    "ScoreContext",
    "Scorer",
    "StopReason",
    "Task",
    "TaskProvider",
    "TaskResult",
    "TaskStatus",
    "Timing",
    "ToolRegistry",
    "ToolSpec",
    "Usage",
    "WebOps",
    "ensure_tool_ops_compatible",
    "validate_agent",
    "validate_agent_variant",
    "validate_env_spec",
    "build_tool_spec",
    "bind_agent_variant",
    "get_default_tool_registry",
    "make_agent_variant",
    "resolve_tool_spec",
    "tool",
    "task",
    "agent",
    "scorer",
    "validate_scorer",
    "validate_scores",
    "validate_task",
    "validate_task_provider",
    "validate_task_result",
]
