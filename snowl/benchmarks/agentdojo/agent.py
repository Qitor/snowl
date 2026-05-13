"""AgentDojo agent: ReActAgent wired with StatefulToolExecutor middleware.

Framework role:
- Creates a ReActAgent with stateful stub tools and a StatefulToolExecutor
  middleware that intercepts sentinel results and delegates to real Python
  tool implementations that mutate shared environment state.
- After the agent finishes, records post_state and state_diff in the output trace.

Runtime/usage wiring:
- Used via `AgentDojoAgent` factory in `examples/agentdojo/agent.py`.
- Consumes sample metadata (suite, tool_schemas, pre_state) from the adapter.

Change guardrails:
- The StatefulToolExecutor must be the only middleware; composition order matters.
"""

from __future__ import annotations

import json
from typing import Any

from snowl.agents.react_agent import ReActAgent
from snowl.core.agent import AgentContext, AgentState, StopReason
from snowl.model import OpenAICompatibleChatClient
from snowl.tools.stateful_executor import StatefulToolExecutor, make_stateful_stub_tool


class AgentDojoAgent:
    """Agent for AgentDojo eval that wires ReActAgent + StatefulToolExecutor."""

    agent_id: str = "agentdojo_agent"

    def __init__(
        self,
        *,
        model_client: OpenAICompatibleChatClient,
        suite: str = "banking",
        max_steps: int = 10,
        toolkit_data: dict[str, Any] | None = None,
    ) -> None:
        self.model_client = model_client
        self.suite = suite
        self.max_steps = max_steps
        self.toolkit_data = toolkit_data or {}

    async def run(
        self,
        state: AgentState,
        context: AgentContext,
        tools: Any | None = None,
    ) -> AgentState:
        # Extract sample metadata
        sample_meta = context.metadata.get("sample", {}).get("metadata", {})
        if not sample_meta:
            # Fallback: metadata may be at top level
            sample_meta = context.metadata

        suite = sample_meta.get("suite") or self.suite
        tool_schemas = sample_meta.get("tool_schemas") or []
        pre_state = sample_meta.get("pre_state") or {}

        # Create StatefulToolExecutor with pre_state
        executor = StatefulToolExecutor(
            suite=suite,
            initial_state=pre_state,
        )

        # Build stub tools from tool schemas
        stub_tools = []
        for schema in tool_schemas:
            fn = schema.get("function", schema)
            name = fn.get("name", "")
            description = fn.get("description", f"Tool {name}.")
            parameters = fn.get("parameters", {"type": "object", "properties": {}})
            if name:
                stub_tools.append(make_stateful_stub_tool(name, description, parameters))

        # Create ReActAgent with executor middleware
        react = ReActAgent(
            model_client=self.model_client,
            agent_id=self.agent_id,
            max_steps=self.max_steps,
            middlewares=[executor],
        )

        result_state = await react.run(state, context, tools=stub_tools)

        # Record stateful execution results in the output trace
        if result_state.output is None:
            result_state.output = {}
        result_state.output["agentdojo_post_state"] = executor.get_post_state()
        result_state.output["agentdojo_state_diff"] = executor.get_state_diff()

        return result_state
