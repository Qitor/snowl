"""Agent contracts, decorator helpers, and normalized runtime types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from snowl.core.declarations import declare
from snowl.errors import SnowlValidationError


class StopReason(str, Enum):
    COMPLETED = "completed"
    MAX_STEPS = "max_steps"
    LIMIT_EXCEEDED = "limit_exceeded"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Action:
    action_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    observation_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentState:
    messages: list[Mapping[str, Any]] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    output: dict[str, Any] | None = None
    stop_reason: StopReason | None = None


@dataclass(frozen=True)
class AgentContext:
    task_id: str
    sample_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Agent(Protocol):
    """Normalized agent contract for native and adapted agents."""

    agent_id: str

    async def run(
        self,
        state: AgentState,
        context: AgentContext,
        tools: Sequence[Any] | None = None,
    ) -> AgentState: ...


def agent(
    value: Any | None = None,
    *,
    agent_id: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Declare an agent object/factory for eval autodiscovery."""

    if agent_id is not None and (not isinstance(agent_id, str) or not agent_id.strip()):
        raise SnowlValidationError("Decorator @agent(...): 'agent_id' must be a non-empty string.")

    def _decorate(inner: Any) -> Any:
        declared_id = agent_id.strip() if isinstance(agent_id, str) and agent_id.strip() else None
        if declared_id is not None and hasattr(inner, "agent_id"):
            try:
                setattr(inner, "agent_id", declared_id)
            except Exception:
                pass
        return declare(inner, kind="agent", object_id=declared_id, metadata=metadata)

    if value is not None:
        return _decorate(value)
    return _decorate


def validate_agent(agent: Any) -> None:
    if not hasattr(agent, "agent_id"):
        raise SnowlValidationError("Agent must define a non-empty 'agent_id'.")

    agent_id = getattr(agent, "agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise SnowlValidationError("Agent.agent_id must be a non-empty string.")

    run_fn = getattr(agent, "run", None)
    if run_fn is None or not callable(run_fn):
        raise SnowlValidationError("Agent must implement callable async 'run(...)'.")
