"""Custom adapter — wrap bare async functions as Snowl Agents.

Framework role:
- Provides ``CustomAdapter`` for agents that don't use any framework.
- Wraps ``async def agent_fn(messages, tools) -> messages`` into the Agent Protocol.

Runtime/usage wiring:
- Used when ``project.yml`` declares ``framework: custom``.
- Simplest possible adapter: no state translation, no tool bridging.

Reference:
- ``references/harbor/src/harbor/agents/base.py`` (BaseAgent pattern)
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable

from snowl.adapters.base import BaseFrameworkAdapter
from snowl.core.agent import AgentState, StopReason


class _CustomAgent:
    """Snowl Agent wrapper around a bare async function."""

    def __init__(self, agent_fn: Callable[..., Awaitable[Any]], agent_id: str = "custom") -> None:
        self._fn = agent_fn
        self.agent_id = agent_id

    async def run(self, state: AgentState, context, tools=None) -> AgentState:
        result = await self._fn(state.messages, tools)

        if isinstance(result, AgentState):
            return result

        # If the function returned a message-like dict or string, wrap it
        if isinstance(result, str):
            content = result
        elif isinstance(result, dict):
            content = result.get("content", str(result))
        elif isinstance(result, list) and result:
            # Assume list of messages — take last assistant message
            last = result[-1] if isinstance(result[-1], dict) else {"content": str(result[-1])}
            content = last.get("content", str(last))
        else:
            content = str(result)

        state.messages.append({"role": "assistant", "content": content})
        state.output = {
            "message": {"role": "assistant", "content": content},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
        state.stop_reason = StopReason.COMPLETED
        return state


class CustomAdapter(BaseFrameworkAdapter):
    """Adapter for bare async function agents."""

    @property
    def framework_name(self) -> str:
        return "custom"

    def wrap(self, agent: Any, **kwargs: Any) -> _CustomAgent:
        """Wrap an async function or callable as a Snowl Agent.

        Args:
            agent: An async callable ``(messages, tools) -> result``.
            **kwargs: Optional ``agent_id`` override.

        Returns:
            A Snowl Agent implementation.
        """
        if not callable(agent):
            raise TypeError(f"CustomAdapter expects a callable, got {type(agent).__name__}")
        return _CustomAgent(agent, agent_id=kwargs.get("agent_id", "custom"))
