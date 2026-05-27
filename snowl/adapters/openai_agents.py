"""OpenAI Agents SDK adapter — wrap OpenAI Agents as Snowl Agents.

Framework role:
- Provides ``OpenAIAgentsAdapter`` for agents built with the OpenAI Agents SDK.
- Bridges OpenAI's ``client.responses.create()`` into Snowl's ``Agent.run()``.

Runtime/usage wiring:
- Used when ``project.yml`` declares ``framework: openai_agents``.
- Supports model selection and tool call tracing.

Reference:
- ``examples/agents/openai-sdk-style/agent.py`` (existing manual wrapper)
"""

from __future__ import annotations

from typing import Any

from snowl.adapters.base import BaseFrameworkAdapter
from snowl.core.agent import AgentState, StopReason


class _OpenAIAgentsAgent:
    """Snowl Agent wrapper around an OpenAI Agents SDK agent."""

    def __init__(
        self,
        client: Any,
        *,
        model: str = "gpt-4.1-mini",
        agent_id: str = "openai_agents",
        **kwargs: Any,
    ) -> None:
        self.client = client
        self.model = model
        self.agent_id = agent_id
        self._kwargs = kwargs

    async def run(self, state: AgentState, context, tools=None) -> AgentState:
        if self.client is None:
            state.output = {
                "message": {"role": "assistant", "content": "OpenAI client not configured."},
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "trace_events": [],
            }
            state.stop_reason = StopReason.COMPLETED
            return state

        messages = [dict(m) for m in state.messages]

        response = await self.client.responses.create(
            model=self.model,
            input=messages,
        )

        content = getattr(response, "output_text", "") or ""

        # Extract usage if available
        usage_info = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        resp_usage = getattr(response, "usage", None)
        if resp_usage:
            usage_info["input_tokens"] = getattr(resp_usage, "input_tokens", 0) or 0
            usage_info["output_tokens"] = getattr(resp_usage, "output_tokens", 0) or 0
            usage_info["total_tokens"] = getattr(resp_usage, "total_tokens", 0) or 0

        # Enrich trace events with per-tool-call details from response output items
        trace_events: list[dict[str, Any]] = [{
            "event": "agent.openai_agents.call",
            "model": self.model,
        }]

        output_items = getattr(response, "output", None)
        if isinstance(output_items, (list, tuple)):
            for item in output_items:
                item_type = getattr(item, "type", "")
                if item_type == "function_call":
                    fn = getattr(item, "function", None) or {}
                    trace_events.append({
                        "event": "agent.openai_agents.tool_call",
                        "tool_name": getattr(fn, "name", None) or (fn.get("name") if isinstance(fn, dict) else ""),
                        "tool_args": getattr(fn, "arguments", None) or (fn.get("arguments") if isinstance(fn, dict) else {}),
                        "call_id": getattr(item, "id", None) or getattr(item, "call_id", None),
                    })
                elif item_type == "function_call_output":
                    trace_events.append({
                        "event": "agent.openai_agents.tool_result",
                        "call_id": getattr(item, "call_id", None),
                        "result_preview": str(getattr(item, "output", ""))[:500],
                    })

        state.messages.append({"role": "assistant", "content": content})
        state.output = {
            "message": {"role": "assistant", "content": content},
            "usage": usage_info,
            "trace_events": trace_events,
        }
        state.stop_reason = StopReason.COMPLETED
        return state


class OpenAIAgentsAdapter(BaseFrameworkAdapter):
    """Adapter for OpenAI Agents SDK agents."""

    @property
    def framework_name(self) -> str:
        return "openai_agents"

    def wrap(self, agent: Any, **kwargs: Any) -> _OpenAIAgentsAgent:
        """Wrap an OpenAI client as a Snowl Agent.

        Args:
            agent: An OpenAI client instance.
            **kwargs: Must include ``model`` (default: 'gpt-4.1-mini').
                Optional ``agent_id`` override.

        Returns:
            A Snowl Agent implementation.
        """
        client = agent
        model = kwargs.pop("model", "gpt-4.1-mini")
        agent_id = kwargs.pop("agent_id", "openai_agents")
        return _OpenAIAgentsAgent(client, model=model, agent_id=agent_id, **kwargs)

    def unwrap_state(self, snowl_state: AgentState) -> Any:
        """Convert Snowl AgentState to OpenAI messages list."""
        return [dict(m) for m in snowl_state.messages]

    def wrap_result(self, framework_result: Any, snowl_state: AgentState) -> AgentState:
        """Convert OpenAI response to Snowl AgentState."""
        content = getattr(framework_result, "output_text", "") or str(framework_result)
        return AgentState(
            messages=snowl_state.messages + [{"role": "assistant", "content": content}],
            output=content,
            stop_reason=StopReason.COMPLETED,
        )

    def wrap_tools(self, snowl_tools: list[Any] | None = None) -> list[dict[str, Any]] | None:
        """Convert Snowl tool specs to OpenAI function tool format.

        Each Snowl ToolSpec with name/description/parameters is converted to an
        OpenAI function definition dict. Returns None if no tools provided.
        """
        if not snowl_tools:
            return None

        openai_tools: list[dict[str, Any]] = []
        for tool in snowl_tools:
            if isinstance(tool, dict):
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                    },
                })
            elif hasattr(tool, "name"):
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": getattr(tool, "name", ""),
                        "description": getattr(tool, "description", ""),
                        "parameters": getattr(tool, "parameters", {"type": "object", "properties": {}}),
                    },
                })

        return openai_tools or None
