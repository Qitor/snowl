"""AgentSafetyBench agent: ReActAgent wired with AgentSafetyBenchExecutor middleware.

Framework role:
- Creates a ReActAgent with environment-specific stub tools and executor
  middleware that intercepts sentinel results and delegates to real Python
  tool implementations from the Agent-SafetyBench environments directory.

Runtime/usage wiring:
- Used via AgentSafetyBenchAgent in examples/agentsafetybench/agent.py.
- Consumes sample metadata (tool_schemas, environments, dialog) from the adapter.

Change guardrails:
- Must not import from the Agent-SafetyBench Python package.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from snowl.agents.react_agent import ReActAgent
from snowl.core import AgentContext, AgentState
from snowl.model import OpenAICompatibleChatClient

from snowl.benchmarks.agentsafetybench.env_loader import AGENTSAFETYBENCH_ENV_DIR
from snowl.benchmarks.agentsafetybench.executor import (
    AgentSafetyBenchExecutor,
    make_agentsafetybench_stub_tool,
)


class AgentSafetyBenchAgent:
    """Agent for AgentSafetyBench eval that wires ReActAgent + environment executors."""

    agent_id: str = "agentsafetybench_agent"

    def __init__(
        self,
        *,
        model_client: OpenAICompatibleChatClient,
        max_steps: int = 10,
        env_dir: str | None = None,
    ) -> None:
        self.model_client = model_client
        self.max_steps = max_steps
        self.env_dir = env_dir or str(AGENTSAFETYBENCH_ENV_DIR)

    async def run(
        self,
        state: AgentState,
        context: AgentContext,
        tools: Any | None = None,
    ) -> AgentState:
        # Extract sample metadata
        sample_meta = context.metadata
        if not sample_meta:
            sample_meta = {}

        tool_schemas = sample_meta.get("tool_schemas") or []
        environments = sample_meta.get("environments") or []
        dialog = sample_meta.get("dialog") or []
        has_env = sample_meta.get("has_environments", False)
        instruction = sample_meta.get("case", {}).get("instruction", "") or sample_meta.get("input", "")

        # Build initial messages from dialog or instruction
        messages: list[dict[str, Any]] = []
        if dialog:
            messages.extend(deepcopy(dialog))
        elif instruction:
            messages.append({"role": "user", "content": instruction})

        # Build stub tools and executor middleware
        stub_tools = []
        middlewares = []
        if has_env:
            for env_info in environments:
                env_name = env_info.get("name", "")
                if not env_name:
                    continue
                env_tool_names = env_info.get("tools") or []
                env_params = env_info.get("parameters") or {}
                executor = AgentSafetyBenchExecutor(
                    env_name=env_name,
                    env_params=env_params,
                    tool_names=env_tool_names,
                    env_dir=self.env_dir,
                )
                middlewares.append(executor)

            for schema in tool_schemas:
                fn = schema.get("function", schema)
                name = fn.get("name", "")
                description = fn.get("description", f"Tool {name}.")
                parameters = fn.get("parameters", {"type": "object", "properties": {}})
                if name:
                    stub_tools.append(make_agentsafetybench_stub_tool(name, description, parameters))

        # Create ReActAgent with executor middleware
        react = ReActAgent(
            model_client=self.model_client,
            agent_id=self.agent_id,
            max_steps=self.max_steps,
            middlewares=middlewares if middlewares else None,
        )

        # Set up initial state with pre-seeded messages
        initial_state = AgentState(
            messages=messages,
            actions=[],
            observations=[],
            output=None,
            stop_reason=None,
        )

        result_state = await react.run(initial_state, context, tools=stub_tools if stub_tools else None)

        # Record execution info in output
        if result_state.output is None:
            result_state.output = {}
        result_state.output["agentsafetybench_environments"] = [
            {"name": e.get("name"), "tools": e.get("tools")}
            for e in environments
        ]

        return result_state
