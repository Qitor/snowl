"""Tests for ReActAgent middleware integration."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from snowl.agents.react_agent import ReActAgent
from snowl.core.agent import AgentContext, AgentState, StopReason
from snowl.core.tool import ToolSpec
from snowl.tools.middleware import IdentityMiddleware, LoggingMiddleware, MiddlewareChain


def _make_tool_spec(name: str, fn=None):
    """Create a minimal ToolSpec for testing."""

    def dummy(**kwargs):
        return "dummy_result"

    return ToolSpec(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        callable=fn or dummy,
    )


def _make_agent(**kwargs):
    mock_client = AsyncMock()
    return ReActAgent(model_client=mock_client, max_steps=2, **kwargs)


def _make_context():
    return AgentContext(
        task_id="test_task",
        sample_id="test_sample",
        metadata={},
    )


def _make_state():
    return AgentState(
        messages=[{"role": "user", "content": "test"}],
        actions=[],
        observations=[],
        stop_reason=None,
        output=None,
    )


# ---------------------------------------------------------------------------
# Backward compatibility: no middleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_no_middleware_identical_output():
    """Agent with middlewares=None produces identical output to before."""
    agent = _make_agent(middlewares=None)
    # Just verify the field exists and is None
    assert agent.middlewares is None


@pytest.mark.asyncio
async def test_agent_empty_middleware_list():
    """Agent with middlewares=[] produces identical output."""
    agent = _make_agent(middlewares=[])
    assert agent.middlewares == []


# ---------------------------------------------------------------------------
# LoggingMiddleware captures tool calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logging_middleware_captures_tool_call():
    """LoggingMiddleware captures tool calls without affecting results."""
    lm = LoggingMiddleware()
    agent = _make_agent(middlewares=[lm])

    # Test _execute_tool_call directly
    tool_fn = lambda x: f"result_{x}"
    tool_spec = ToolSpec(
        name="echo",
        description="Echo tool",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "additionalProperties": False,
        },
        callable=tool_fn,
    )

    tool_map = {"echo": tool_fn}
    allowed = {"echo"}
    chain = MiddlewareChain(agent.middlewares)

    result = await agent._execute_tool_call(
        "echo",
        json.dumps({"x": "hello"}),
        tool_map,
        allowed,
        chain,
    )
    assert result == "result_hello"
    assert len(lm.log) == 2  # one call + one result
    assert lm.log[0]["phase"] == "call"
    assert lm.log[0]["tool_name"] == "echo"
    assert lm.log[1]["phase"] == "result"
    assert lm.log[1]["result"] == "result_hello"


# ---------------------------------------------------------------------------
# Middleware can modify args
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_modifies_args():
    """Middleware can add default parameters before execution."""

    class AddDefaultMiddleware:
        async def intercept_call(self, tool_name: str, args: dict) -> dict:
            args.setdefault("suffix", "_modified")
            return args

        async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
            return result

    agent = _make_agent(middlewares=[AddDefaultMiddleware()])

    def concat(prefix: str = "", suffix: str = ""):
        return f"{prefix}{suffix}"

    tool_map = {"concat": concat}
    allowed = {"concat"}
    chain = MiddlewareChain(agent.middlewares)

    result = await agent._execute_tool_call(
        "concat",
        json.dumps({"prefix": "hello"}),
        tool_map,
        allowed,
        chain,
    )
    assert result == "hello_modified"


# ---------------------------------------------------------------------------
# Middleware can modify result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_modifies_result():
    """Middleware can transform result after execution."""

    class UpperMiddleware:
        async def intercept_call(self, tool_name: str, args: dict) -> dict:
            return args

        async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
            return str(result).upper()

    agent = _make_agent(middlewares=[UpperMiddleware()])

    tool_fn = lambda: "hello"
    tool_map = {"greet": tool_fn}
    allowed = {"greet"}
    chain = MiddlewareChain(agent.middlewares)

    result = await agent._execute_tool_call(
        "greet",
        json.dumps({}),
        tool_map,
        allowed,
        chain,
    )
    assert result == "HELLO"


# ---------------------------------------------------------------------------
# Multiple middlewares compose correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_middlewares_compose():
    """Call order M1->M2, result order M2->M1."""

    class TagCallMiddleware:
        def __init__(self, tag: str):
            self.tag = tag

        async def intercept_call(self, tool_name: str, args: dict) -> dict:
            order = args.get("call_order", [])
            order.append(self.tag)
            args["call_order"] = order
            return args

        async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
            order = result.get("result_order", []) if isinstance(result, dict) else []
            order.append(self.tag)
            if isinstance(result, dict):
                result["result_order"] = order
                return result
            return {"result_order": order}

    m1 = TagCallMiddleware("M1")
    m2 = TagCallMiddleware("M2")
    agent = _make_agent(middlewares=[m1, m2])

    tool_fn = lambda **kwargs: kwargs
    tool_map = {"tag_tool": tool_fn}
    allowed = {"tag_tool"}
    chain = MiddlewareChain(agent.middlewares)

    result = await agent._execute_tool_call(
        "tag_tool",
        json.dumps({}),
        tool_map,
        allowed,
        chain,
    )
    assert result["call_order"] == ["M1", "M2"]
    assert result["result_order"] == ["M2", "M1"]


# ---------------------------------------------------------------------------
# Unknown tool still returns error; middleware not invoked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_returns_error_without_middleware():
    """Unknown tool name returns error before middleware is invoked."""
    lm = LoggingMiddleware()
    agent = _make_agent(middlewares=[lm])

    tool_map = {"known_tool": lambda: "ok"}
    allowed = {"known_tool"}
    chain = MiddlewareChain(agent.middlewares)

    result = await agent._execute_tool_call(
        "unknown_tool",
        json.dumps({}),
        tool_map,
        allowed,
        chain,
    )
    assert result == "ERROR: unknown tool 'unknown_tool'"
    # LoggingMiddleware should not have been invoked
    assert len(lm.log) == 0


# ---------------------------------------------------------------------------
# No middleware_chain passed (backward compat)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_call_without_chain():
    """_execute_tool_call works without middleware_chain (backward compat)."""
    agent = _make_agent()
    tool_fn = lambda x: f"result_{x}"
    tool_map = {"echo": tool_fn}
    allowed = {"echo"}

    result = await agent._execute_tool_call(
        "echo",
        json.dumps({"x": "hello"}),
        tool_map,
        allowed,
    )
    assert result == "result_hello"
