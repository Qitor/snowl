"""LangGraph adapter — wrap LangGraph compiled graphs as Snowl Agents.

Framework role:
- Provides ``LangGraphAdapter`` for agents built with LangGraph.
- Bridges LangGraph's ``graph.ainvoke()`` into Snowl's ``Agent.run()``.

Runtime/usage wiring:
- Used when ``project.yml`` declares ``framework: langgraph``.
- Supports streaming and tool call tracing.

Reference:
- ``references/harbor/src/harbor/agents/factory.py`` (import_path loading)
- ``examples/agents/langgraph-wrapper/agent.py`` (existing manual wrapper)
"""

from __future__ import annotations

from typing import Any

from snowl.adapters.base import BaseFrameworkAdapter
from snowl.core.agent import AgentState, StopReason


class _LangGraphAgent:
    """Snowl Agent wrapper around a LangGraph compiled graph."""

    def __init__(self, graph: Any, *, agent_id: str = "langgraph", **kwargs: Any) -> None:
        self.graph = graph
        self.agent_id = agent_id
        self._kwargs = kwargs

    async def run(self, state: AgentState, context, tools=None) -> AgentState:
        if self.graph is None:
            state.output = {
                "message": {"role": "assistant", "content": "LangGraph graph not configured."},
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "trace_events": [],
            }
            state.stop_reason = StopReason.COMPLETED
            return state

        # Build LangGraph input from Snowl state
        graph_input = {
            "messages": [dict(m) for m in state.messages],
            "task_id": context.task_id,
            "sample_id": context.sample_id,
            "metadata": dict(context.metadata),
        }

        # Try streaming events for richer trace; fall back to ainvoke
        trace_events: list[dict[str, Any]] = []
        usage_info = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        content = ""

        try:
            async for event in self.graph.astream_events(graph_input, version="v2"):
                kind = event.get("event", "")

                if kind == "on_chain_start":
                    name = event.get("name", "")
                    if name and name != "LangGraph":
                        trace_events.append({
                            "event": "agent.langgraph.node.start",
                            "node": name,
                        })

                elif kind == "on_chain_end":
                    name = event.get("name", "")
                    output = event.get("data", {}).get("output")
                    if name and name != "LangGraph":
                        evt: dict[str, Any] = {
                            "event": "agent.langgraph.node.end",
                            "node": name,
                        }
                        # Check for tool calls in node output
                        if isinstance(output, dict):
                            messages = output.get("messages", [])
                            if isinstance(messages, list):
                                for msg in messages:
                                    if isinstance(msg, dict) and msg.get("tool_calls"):
                                        for tc in msg["tool_calls"]:
                                            trace_events.append({
                                                "event": "agent.langgraph.tool_call",
                                                "tool_name": tc.get("name", tc.get("function", {}).get("name", "")),
                                                "tool_args": tc.get("args", tc.get("function", {}).get("arguments", {})),
                                                "call_id": tc.get("id"),
                                            })
                                    elif hasattr(msg, "tool_calls") and msg.tool_calls:
                                        for tc in msg.tool_calls:
                                            trace_events.append({
                                                "event": "agent.langgraph.tool_call",
                                                "tool_name": getattr(tc, "name", ""),
                                                "tool_args": getattr(tc, "args", {}),
                                                "call_id": getattr(tc, "id", None),
                                            })
                        trace_events.append(evt)

                elif kind == "on_chat_model_end":
                    output_data = event.get("data", {}).get("output", {})
                    # Extract usage from LLM calls
                    llm_usage = getattr(output_data, "usage_metadata", None) if hasattr(output_data, "usage_metadata") else None
                    if not llm_usage and isinstance(output_data, dict):
                        llm_usage = output_data.get("usage_metadata")
                    if llm_usage:
                        usage_info["input_tokens"] += getattr(llm_usage, "input_tokens", 0) or llm_usage.get("input_tokens", 0) or 0
                        usage_info["output_tokens"] += getattr(llm_usage, "output_tokens", 0) or llm_usage.get("output_tokens", 0) or 0
                        usage_info["total_tokens"] += getattr(llm_usage, "total_tokens", 0) or llm_usage.get("total_tokens", 0) or 0
        except (AttributeError, TypeError):
            # astream_events not available or graph doesn't support it; fall back to ainvoke
            result = await self.graph.ainvoke(graph_input)
            if isinstance(result, dict):
                content = str(result.get("output") or result.get("content") or "")
                trace_events.append({
                    "event": "agent.langgraph.invoke",
                    "keys": sorted(result.keys()),
                })
                # Try to extract usage from result metadata
                meta = result.get("metadata") or {}
                if isinstance(meta, dict):
                    total_in = meta.get("input_tokens", 0) or 0
                    total_out = meta.get("output_tokens", 0) or 0
                    if total_in or total_out:
                        usage_info["input_tokens"] = total_in
                        usage_info["output_tokens"] = total_out
                        usage_info["total_tokens"] = total_in + total_out
            else:
                content = str(result)
                trace_events.append({
                    "event": "agent.langgraph.invoke",
                    "type": type(result).__name__,
                })

        # Extract final content from last trace event if not set
        if not content and trace_events:
            # Look for the last assistant message in graph output
            pass  # content remains empty if streaming didn't produce it

        # Fallback: run ainvoke to get final output if streaming didn't capture it
        if not content:
            result = await self.graph.ainvoke(graph_input)
            if isinstance(result, dict):
                content = str(result.get("output") or result.get("content") or "")
            else:
                content = str(result)

        state.messages.append({"role": "assistant", "content": content})
        state.output = {
            "message": {"role": "assistant", "content": content},
            "usage": usage_info,
            "trace_events": trace_events,
        }
        state.stop_reason = StopReason.COMPLETED
        return state


class LangGraphAdapter(BaseFrameworkAdapter):
    """Adapter for LangGraph compiled graph agents."""

    @property
    def framework_name(self) -> str:
        return "langgraph"

    def wrap(self, agent: Any, **kwargs: Any) -> _LangGraphAgent:
        """Wrap a LangGraph compiled graph as a Snowl Agent.

        Args:
            agent: A compiled LangGraph graph with ``ainvoke()`` method.
            **kwargs: Optional ``agent_id`` override.

        Returns:
            A Snowl Agent implementation.
        """
        if agent is not None and not hasattr(agent, "ainvoke"):
            raise TypeError(
                f"LangGraphAdapter expects a compiled graph with ainvoke(), "
                f"got {type(agent).__name__}"
            )
        return _LangGraphAgent(agent, agent_id=kwargs.get("agent_id", "langgraph"), **kwargs)

    def unwrap_state(self, snowl_state: AgentState) -> Any:
        """Convert Snowl AgentState to LangGraph input dict."""
        return {"messages": [dict(m) for m in snowl_state.messages]}

    def wrap_result(self, framework_result: Any, snowl_state: AgentState) -> AgentState:
        """Convert LangGraph result dict to Snowl AgentState."""
        if isinstance(framework_result, dict):
            content = str(framework_result.get("output") or framework_result.get("content") or "")
        else:
            content = str(framework_result)
        return AgentState(
            messages=snowl_state.messages + [{"role": "assistant", "content": content}],
            output=content,
            stop_reason=StopReason.COMPLETED,
        )

    def wrap_tools(self, snowl_tools: list[Any] | None = None) -> Any:
        """Convert Snowl tool specs to LangGraph tool format.

        Returns None since LangGraph typically manages its own tools.
        """
        return None
