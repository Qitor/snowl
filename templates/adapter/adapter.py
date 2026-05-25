"""Framework adapter template — copy and customize for your agent framework.

Steps:
1. Copy this file to snowl/adapters/<framework_name>.py
2. Implement run() to bridge between your framework and Snowl Agent Protocol
3. Register in snowl/adapters/registry.py
4. Test with: project.yml agent_type: <framework_name>

Replace all placeholder values marked with {{...}}.
"""

from __future__ import annotations

from typing import Any, Sequence

from snowl.adapters.base import BaseFrameworkAdapter
from snowl.core.agent import AgentContext, AgentState


class {{FrameworkName}}Adapter(BaseFrameworkAdapter):
    """Adapter for running {{framework_name}} agents in Snowl evaluations."""

    framework_name = "{{framework_name}}"

    def adapt(self, agent_module: Any, **kwargs: Any) -> Any:
        """Wrap a {{framework_name}} agent module as a Snowl Agent.

        The returned object must satisfy the Agent Protocol:
        - agent_id: str
        - async def run(state: AgentState, context: AgentContext, tools=None) -> AgentState
        """
        class WrappedAgent:
            agent_id = f"{{framework_name}}:{getattr(agent_module, 'name', 'default')}"

            async def run(
                self,
                state: AgentState,
                context: AgentContext,
                tools: Sequence[Any] | None = None,
            ) -> AgentState:
                # TODO: Extract the task input from state.messages
                # TODO: Call the framework's agent entry point
                # TODO: Parse the result back into AgentState
                return state

        return WrappedAgent()
