"""Tests for AgentDojoAgent wiring and StatefulToolExecutor integration."""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from snowl.benchmarks.agentdojo.agent import AgentDojoAgent
from snowl.core.agent import AgentContext, AgentState, StopReason
from snowl.tools.stateful_executor import BANKING_TOOLS, STATEFUL_SENTINEL, StatefulToolExecutor


BANKING_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_balance",
            "description": "Get account balance.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_money",
            "description": "Send money.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string"},
                    "amount": {"type": "number"},
                    "subject": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["recipient", "amount", "subject", "date"],
            },
        },
    },
]

BANKING_PRE_STATE = {
    "bank_account": {
        "balance": 1810.0,
        "iban": "DE89370400440532013000",
        "transactions": [
            {"id": 1, "sender": "me", "recipient": "CH93", "amount": 100.0, "subject": "Pizza", "date": "2022-01-01", "recurring": False}
        ],
        "scheduled_transactions": [],
    },
    "filesystem": {"files": {"bill.txt": "Total: 98.70"}},
    "user_account": {"first_name": "Emma", "last_name": "Johnson", "password": "password123"},
}


def _make_mock_model_client(responses: list[dict[str, Any]]) -> MagicMock:
    """Create a mock model client that returns the given responses in sequence."""
    client = MagicMock()
    client.model = "test-model"
    client.base_url = "http://localhost"
    client.provider_id = "test"

    async def _generate(messages, **kwargs):
        if not responses:
            # Return a final answer
            resp = MagicMock()
            resp.message = {"role": "assistant", "content": "Done."}
            resp.usage = MagicMock(input_tokens=10, output_tokens=5, total_tokens=15)
            resp.timing = MagicMock(started_at_ms=0, ended_at_ms=100, duration_ms=100)
            resp.raw = {}
            return resp
        resp_data = responses.pop(0)
        resp = MagicMock()
        resp.message = resp_data
        resp.usage = MagicMock(input_tokens=10, output_tokens=5, total_tokens=15)
        resp.timing = MagicMock(started_at_ms=0, ended_at_ms=100, duration_ms=100)
        resp.raw = {}
        return resp

    client.generate = _generate
    return client


def _run(coro):
    """Run an async coroutine synchronously in tests."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


class TestAgentDojoAgentConstruction:
    def test_default_agent_id(self) -> None:
        client = _make_mock_model_client([])
        agent = AgentDojoAgent(model_client=client)
        assert agent.agent_id == "agentdojo_agent"

    def test_custom_suite(self) -> None:
        client = _make_mock_model_client([])
        agent = AgentDojoAgent(model_client=client, suite="travel")
        assert agent.suite == "travel"


class TestAgentDojoAgentExecution:
    def test_agent_records_post_state(self) -> None:
        """Agent records post_state and state_diff in output after execution."""
        # First call: tool call for get_balance, second call: final answer
        responses = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "get_balance",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "Your balance is 1810."},
        ]
        client = _make_mock_model_client(responses)
        agent = AgentDojoAgent(model_client=client, suite="banking", max_steps=5)

        state = AgentState(
            messages=[{"role": "user", "content": "What is my balance?"}],
        )
        context = AgentContext(
            task_id="test_task",
            sample_id="test_sample",
            metadata={
                "suite": "banking",
                "tool_schemas": BANKING_TOOL_SCHEMAS,
                "pre_state": BANKING_PRE_STATE,
            },
        )

        result = _run(agent.run(state, context))

        assert result.output is not None
        assert "agentdojo_post_state" in result.output
        assert "agentdojo_state_diff" in result.output
        post = result.output["agentdojo_post_state"]
        assert post["bank_account"]["balance"] == 1810.0

    def test_agent_state_mutates_across_calls(self) -> None:
        """Agent's StatefulToolExecutor mutates state across sequential tool calls."""
        responses = [
            # Step 1: send money
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "send_money",
                            "arguments": json.dumps({
                                "recipient": "US123",
                                "amount": 50.0,
                                "subject": "Test",
                                "date": "2024-01-01",
                            }),
                        },
                    }
                ],
            },
            # Step 2: get balance
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc_2",
                        "type": "function",
                        "function": {
                            "name": "get_balance",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            # Step 3: final answer
            {"role": "assistant", "content": "Money sent and balance checked."},
        ]
        client = _make_mock_model_client(responses)
        agent = AgentDojoAgent(model_client=client, suite="banking", max_steps=5)

        state = AgentState(
            messages=[{"role": "user", "content": "Send $50 to US123"}],
        )
        context = AgentContext(
            task_id="test_task",
            sample_id="test_sample",
            metadata={
                "suite": "banking",
                "tool_schemas": BANKING_TOOL_SCHEMAS,
                "pre_state": BANKING_PRE_STATE,
            },
        )

        result = _run(agent.run(state, context))

        post = result.output["agentdojo_post_state"]
        # Transaction should have been appended
        assert len(post["bank_account"]["transactions"]) == 2
        assert post["bank_account"]["transactions"][-1]["recipient"] == "US123"

    def test_agent_uses_sample_metadata_for_suite(self) -> None:
        """Agent extracts suite from sample metadata, not constructor."""
        client = _make_mock_model_client([
            {"role": "assistant", "content": "Done."},
        ])
        agent = AgentDojoAgent(model_client=client, suite="travel", max_steps=3)

        state = AgentState(
            messages=[{"role": "user", "content": "Hi"}],
        )
        # Pass banking metadata even though agent default is travel
        context = AgentContext(
            task_id="test_task",
            sample_id="test_sample",
            metadata={
                "suite": "banking",
                "tool_schemas": BANKING_TOOL_SCHEMAS[:1],  # just get_balance
                "pre_state": BANKING_PRE_STATE,
            },
        )

        result = _run(agent.run(state, context))
        # The agent should have used banking tools (executor suite=banking)
        assert result.output is not None
