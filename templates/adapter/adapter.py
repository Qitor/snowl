"""Framework adapter template — copy and customize for your agent framework.

Steps:
1. Copy this file to snowl/adapters/<framework_name>.py
2. Implement wrap() to bridge between your framework and Snowl Agent Protocol
3. Register via entry_points in your pyproject.toml:
       [project.entry-points."snowl.adapters"]
       <framework_name> = "snowl.adapters.<framework_name>:<FrameworkName>Adapter"
4. Test with: project.yml agent_type: <framework_name>

Replace all placeholder values marked with {{...}}.
"""

from __future__ import annotations

from typing import Any, Sequence

from snowl.adapters.base import BaseFrameworkAdapter
from snowl.core.agent import AgentContext, AgentState, StopReason


class {{FrameworkName}}Adapter(BaseFrameworkAdapter):
    """Adapter for running {{framework_name}} agents in Snowl evaluations."""

    @property
    def framework_name(self) -> str:
        return "{{framework_name}}"

    def wrap(self, agent: Any, **kwargs: Any) -> Any:
        """Wrap a {{framework_name}} agent as a Snowl Agent.

        The returned object must satisfy the Agent Protocol:
        - agent_id: str
        - async def run(state: AgentState, context: AgentContext, tools=None) -> AgentState
        """
        # Optional: verify the framework is installed
        # self._check_framework_available()

        return _{{FrameworkName}}Agent(agent, config=kwargs)

    # Optional: override these for richer integration

    def unwrap_state(self, snowl_state: AgentState) -> Any:
        """Translate Snowl state to framework-native format.

        Default: pass through. Override to extract the user instruction
        from snowl_state.messages and convert to your framework's input format.
        """
        return snowl_state

    def wrap_result(self, framework_result: Any, snowl_state: AgentState) -> AgentState:
        """Translate framework result back to Snowl AgentState.

        Default: pass through. Override to convert your framework's output
        into messages, usage, and trace_events on snowl_state.
        """
        return snowl_state

    def wrap_tools(self, snowl_tools: Any) -> Any:
        """Convert Snowl tools to framework tools.

        Default: returns None (no tool bridging). Override if your framework
        can consume Snowl tool specs.
        """
        return None

    @staticmethod
    def _check_framework_available() -> None:
        """Verify the framework package is importable.

        Import and raise ImportError with install instructions if missing.
        This keeps snowl importable even when the framework is not installed.
        """
        try:
            import {{framework_name}}  # noqa: F401
        except ImportError:
            raise ImportError(
                "{{framework_name}} is required for the {{FrameworkName}} adapter. "
                "Install it with: pip install {{framework_name}}"
            )


class _{{FrameworkName}}Agent:
    """Agent wrapper that bridges {{framework_name}} to Snowl's Agent Protocol."""

    def __init__(self, agent: Any, config: dict[str, Any] | None = None) -> None:
        self._agent = agent
        self._config = config or {}
        self.agent_id = f"{{framework_name}}:{getattr(agent, 'name', 'default')}"

    async def run(
        self,
        state: AgentState,
        context: AgentContext,
        tools: Sequence[Any] | None = None,
    ) -> AgentState:
        """Execute the {{framework_name}} agent and return updated state."""
        # 1. Extract instruction from state.messages
        #    instruction = state.messages[-1].get("content", "")

        # 2. Call the framework's agent entry point
        #    result = await self._agent.run(instruction, tools=tools, **self._config)

        # 3. Parse the result back into AgentState
        #    state.messages.append({"role": "assistant", "content": result.text})
        #    state.output = {
        #        "trace_events": [...],  # per-step tool calls and observations
        #        "usage": {"input_tokens": ..., "output_tokens": ...},
        #    }
        #    state.stop_reason = StopReason.COMPLETED

        return state
