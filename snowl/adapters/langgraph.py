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

        result = await self.graph.ainvoke(graph_input)

        # Extract output — LangGraph graphs typically return a dict
        content = ""
        trace_events = []

        if isinstance(result, dict):
            content = str(result.get("output") or result.get("content") or "")
            trace_events.append({
                "event": "agent.langgraph.invoke",
                "keys": sorted(result.keys()),
            })
        else:
            content = str(result)
            trace_events.append({
                "event": "agent.langgraph.invoke",
                "type": type(result).__name__,
            })

        state.messages.append({"role": "assistant", "content": content})
        state.output = {
            "message": {"role": "assistant", "content": content},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
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
