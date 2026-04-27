from __future__ import annotations

from snowl.core import StopReason


class OpenAISDKStyleAgent:
    agent_id = "openai-sdk-style"

    def __init__(self, client=None, model: str = "gpt-4.1-mini") -> None:
        self.client = client
        self.model = model

    async def run(self, state, context, tools=None):
        _ = (context, tools)
        messages = list(state.messages)
        if self.client is None:
            content = "OpenAI SDK client not configured; this example shows the wrapper shape."
        else:
            response = await self.client.responses.create(model=self.model, input=messages)
            content = getattr(response, "output_text", "")
        state.output = {
            "message": {"role": "assistant", "content": content},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "trace_events": [{"event": "agent.model_call", "model": self.model}],
        }
        state.stop_reason = StopReason.COMPLETED
        return state


agent = OpenAISDKStyleAgent()
