from __future__ import annotations

import asyncio

import httpx

from snowl.agents import ReActAgent
from snowl.core import AgentContext, AgentState, StopReason, tool
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig


def test_react_agent_runs_tool_then_completes() -> None:
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "I'll use a tool",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "echo",
                                            "arguments": '{"text": "hi"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
                },
            )

        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "done"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            },
        )

    @tool
    def echo(text: str) -> str:
        """Echo text.

        Args:
            text: input text
        """
        return f"ECHO:{text}"

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

    agent = ReActAgent(model_client=client, max_steps=4)
    state = AgentState(messages=[{"role": "user", "content": "go"}])
    context = AgentContext(task_id="task-1", sample_id="sample-1")

    async def _run() -> None:
        out = await agent.run(state, context, tools=[echo])
        assert out.stop_reason == StopReason.COMPLETED
        assert any(a.payload.get("tool_name") == "echo" for a in out.actions)
        assert any(o.observation_type == "tool_result" for o in out.observations)
        assert out.output is not None
        assert out.output["usage"]["total_tokens"] == 8
        assert "{tool_schema}" not in out.messages[0]["content"]
        assert "TOOL SCHEMA (INJECTED AT RUNTIME)" in out.messages[0]["content"]
        await client.aclose()

    asyncio.run(_run())


def test_react_agent_stops_on_max_steps() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "noop", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    @tool
    def noop() -> str:
        """No-op tool."""
        return "ok"

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

    agent = ReActAgent(model_client=client, max_steps=1)
    state = AgentState(messages=[{"role": "user", "content": "go"}])
    context = AgentContext(task_id="task-1", sample_id="sample-1")

    async def _run() -> None:
        out = await agent.run(state, context, tools=[noop])
        assert out.stop_reason == StopReason.MAX_STEPS
        await client.aclose()

    asyncio.run(_run())


def test_react_agent_falls_back_to_json_protocol() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        body = request.read().decode("utf-8")
        if '"tools"' in body:
            return httpx.Response(400, json={"error": {"message": "tools unsupported"}})

        if calls["count"] == 2:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": '{"type":"tool_call","tool":"echo","arguments":{"text":"hi"}}',
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
                },
            )

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"type":"final","answer":"done"}',
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    @tool
    def echo(text: str) -> str:
        """Echo text."""
        return f"ECHO:{text}"

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

    agent = ReActAgent(model_client=client, max_steps=4, enable_json_fallback=True)
    state = AgentState(messages=[{"role": "user", "content": "go"}])
    context = AgentContext(task_id="task-1", sample_id="sample-1")
    async def _run() -> None:
        out = await agent.run(state, context, tools=[echo])
        assert out.stop_reason == StopReason.COMPLETED
        assert any(e.get("event") == "react_agent.fallback_enabled" for e in out.output["trace_events"])
        assert out.messages[-1]["content"] == "done"
        await client.aclose()

    asyncio.run(_run())
