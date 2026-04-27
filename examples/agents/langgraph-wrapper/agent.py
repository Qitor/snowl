from __future__ import annotations

from snowl.core import StopReason


class LangGraphWrapperAgent:
    agent_id = "langgraph-wrapper"

    def __init__(self, graph=None) -> None:
        self.graph = graph

    async def run(self, state, context, tools=None):
        _ = tools
        if self.graph is None:
            content = "LangGraph app not configured; this example shows the wrapper shape."
            trace_events = []
        else:
            result = await self.graph.ainvoke(
                {
                    "messages": list(state.messages),
                    "task_id": context.task_id,
                    "sample_id": context.sample_id,
                    "metadata": dict(context.metadata),
                }
            )
            content = str(result.get("output") or result.get("content") or "")
            trace_events = [{"event": "agent.langgraph.invoke", "keys": sorted(result.keys())}]
        state.output = {
            "message": {"role": "assistant", "content": content},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "trace_events": trace_events,
        }
        state.stop_reason = StopReason.COMPLETED
        return state


agent = LangGraphWrapperAgent()
