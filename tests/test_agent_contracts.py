from __future__ import annotations

import pytest

from snowl.core import AgentContext, AgentState, validate_agent
from snowl.core.tool import ToolSpec
from snowl.errors import SnowlValidationError


class GoodAgent:
    agent_id = "chat-agent"

    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        return state


class MissingIdAgent:
    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        return state


class MissingRunAgent:
    agent_id = "bad-agent"


def test_validate_agent_ok() -> None:
    validate_agent(GoodAgent())


def test_validate_agent_missing_id() -> None:
    with pytest.raises(SnowlValidationError, match="agent_id"):
        validate_agent(MissingIdAgent())


def test_validate_agent_missing_run() -> None:
    with pytest.raises(SnowlValidationError, match="run"):
        validate_agent(MissingRunAgent())


# ---------------------------------------------------------------------------
# ToolSpec.execute
# ---------------------------------------------------------------------------


def _simple_spec(**kwargs):
    return ToolSpec(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        **kwargs,
    )


@pytest.mark.asyncio
async def test_tool_spec_execute_sync_callable():
    def add(a: int, b: int) -> int:
        return a + b

    spec = _simple_spec(callable=add)
    result = await spec.execute(a=1, b=2)
    assert result == 3


@pytest.mark.asyncio
async def test_tool_spec_execute_async_callable():
    async def async_add(a: int, b: int) -> int:
        return a + b

    spec = _simple_spec(callable=lambda: None, async_callable=async_add)
    result = await spec.execute(a=3, b=4)
    assert result == 7


@pytest.mark.asyncio
async def test_tool_spec_execute_prefers_async_callable():
    """When both callable and async_callable are set, async_callable wins."""

    def sync_fn():
        return "sync"

    async def async_fn():
        return "async"

    spec = _simple_spec(callable=sync_fn, async_callable=async_fn)
    result = await spec.execute()
    assert result == "async"


@pytest.mark.asyncio
async def test_tool_spec_execute_callable_returning_awaitable():
    """Sync callable that returns an awaitable is awaited."""

    async def coro():
        return "coro_result"

    def sync_returns_coro():
        return coro()

    spec = _simple_spec(callable=sync_returns_coro)
    result = await spec.execute()
    assert result == "coro_result"


@pytest.mark.asyncio
async def test_tool_spec_execute_raises_without_callable():
    spec = ToolSpec(
        name="broken",
        description="No callable",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        callable=None,
    )
    with pytest.raises(RuntimeError, match="no callable"):
        await spec.execute()
