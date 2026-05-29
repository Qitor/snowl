"""Snowl adapter for {{cookiecutter.adapter_name}}.

This module bridges {{cookiecutter.adapter_name}} agents to Snowl's Agent Protocol,
enabling any {{cookiecutter.adapter_name}} agent to run in Snowl evaluations.
"""

from __future__ import annotations

from typing import Any, Sequence

from snowl.adapters.base import BaseFrameworkAdapter
from snowl.core.agent import AgentContext, AgentState, StopReason


class {{cookiecutter.class_name}}(BaseFrameworkAdapter):
    """Adapter for running {{cookiecutter.adapter_name}} agents in Snowl evaluations."""

    @property
    def framework_name(self) -> str:
        return "{{cookiecutter.framework_name}}"

    def wrap(self, agent: Any, **kwargs: Any) -> Any:
        """Wrap a {{cookiecutter.adapter_name}} agent as a Snowl Agent."""
        self._check_framework_available()
        return _WrappedAgent(agent, config=kwargs)

    def unwrap_state(self, snowl_state: AgentState) -> Any:
        """Translate Snowl state to {{cookiecutter.adapter_name}} format."""
        # Extract instruction from last user message
        messages = snowl_state.messages or []
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""

    def wrap_result(self, framework_result: Any, snowl_state: AgentState) -> AgentState:
        """Translate {{cookiecutter.adapter_name}} result to Snowl AgentState."""
        # TODO: Convert framework_result to messages, trace_events, usage
        # Example:
        #   snowl_state.messages.append({"role": "assistant", "content": str(framework_result)})
        #   snowl_state.stop_reason = StopReason.COMPLETED
        return snowl_state

    def wrap_tools(self, snowl_tools: Any) -> Any:
        """Convert Snowl tools to {{cookiecutter.adapter_name}} tools."""
        # TODO: Bridge Snowl tool specs to framework-native tool format
        return None

    @staticmethod
    def _check_framework_available() -> None:
        try:
            import {{cookiecutter.framework_name}}  # noqa: F401
        except ImportError:
            raise ImportError(
                "{{cookiecutter.adapter_name}} is required for this adapter. "
                "Install it with: pip install {{cookiecutter.framework_name}}"
            )


class _WrappedAgent:
    """Agent wrapper bridging {{cookiecutter.adapter_name}} to Snowl Agent Protocol."""

    def __init__(self, agent: Any, config: dict[str, Any] | None = None) -> None:
        self._agent = agent
        self._config = config or {}
        self.agent_id = f"{{cookiecutter.framework_name}}:{getattr(agent, 'name', 'default')}"

    async def run(
        self,
        state: AgentState,
        context: AgentContext,
        tools: Sequence[Any] | None = None,
    ) -> AgentState:
        """Execute the {{cookiecutter.adapter_name}} agent and return updated state."""
        # TODO: Implement the agent execution bridge
        # 1. Extract instruction from state.messages
        # 2. Call framework agent
        # 3. Populate state.messages, state.output, state.stop_reason
        state.stop_reason = StopReason.COMPLETED
        return state
