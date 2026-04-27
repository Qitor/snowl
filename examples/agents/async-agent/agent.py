from __future__ import annotations

from snowl.core import StopReason


class AsyncDemoAgent:
    agent_id = "async-demo"

    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {
            "message": {
                "role": "assistant",
                "content": "This is a minimal async Snowl agent response.",
            },
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state


agent = AsyncDemoAgent()
