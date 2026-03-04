from __future__ import annotations

import asyncio

import httpx

from snowl.agents import ChatAgent
from snowl.core import AgentContext, AgentState, StopReason
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig


def test_chat_agent_single_call_sets_output_and_trace() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "42"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            },
        )

    client = OpenAICompatibleChatClient(
        OpenAICompatibleConfig(
            base_url="https://example.com/v1",
            api_key="k",
            model="gpt-test",
            timeout=5,
            max_retries=0,
        ),
        transport=httpx.MockTransport(handler),
    )

    agent = ChatAgent(model_client=client, agent_id="chat_agent")
    state = AgentState(messages=[{"role": "user", "content": "answer?"}])
    context = AgentContext(task_id="task-1", sample_id="sample-1")

    async def _run() -> None:
        out = await agent.run(state, context)
        assert out.stop_reason == StopReason.COMPLETED
        assert out.messages[-1]["role"] == "assistant"
        assert out.messages[-1]["content"] == "42"
        assert out.output is not None
        assert out.output["usage"]["total_tokens"] == 4
        assert out.output["trace_events"][0]["event"] == "chat_agent.generate"
        assert out.observations[-1].observation_type == "model_response"
        await client.aclose()

    asyncio.run(_run())
