"""Tests for ToolMiddleware protocol, MiddlewareChain, and built-in middlewares."""

from __future__ import annotations

import pytest

from snowl.tools.middleware import (
    IdentityMiddleware,
    LoggingMiddleware,
    MiddlewareChain,
    ToolMiddleware,
)


# ---------------------------------------------------------------------------
# MiddlewareChain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_chain_returns_args_unchanged():
    chain = MiddlewareChain([])
    args = {"x": 1}
    result = await chain.run_call("tool_a", args)
    assert result == {"x": 1}


@pytest.mark.asyncio
async def test_empty_chain_returns_result_unchanged():
    chain = MiddlewareChain([])
    result = await chain.run_result("tool_a", {"x": 1}, "original")
    assert result == "original"


@pytest.mark.asyncio
async def test_none_middlewares_returns_args_unchanged():
    chain = MiddlewareChain(None)
    args = {"x": 1}
    result = await chain.run_call("tool_a", args)
    assert result == {"x": 1}


@pytest.mark.asyncio
async def test_single_middleware_intercepts_call():
    class AddDefaultMiddleware:
        async def intercept_call(self, tool_name: str, args: dict) -> dict:
            args.setdefault("default_val", 42)
            return args

        async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
            return result

    from typing import Any

    chain = MiddlewareChain([AddDefaultMiddleware()])
    result = await chain.run_call("tool_a", {"x": 1})
    assert result == {"x": 1, "default_val": 42}


@pytest.mark.asyncio
async def test_single_middleware_intercepts_result():
    class UpperMiddleware:
        async def intercept_call(self, tool_name: str, args: dict) -> dict:
            return args

        async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
            return str(result).upper()

    from typing import Any

    chain = MiddlewareChain([UpperMiddleware()])
    result = await chain.run_result("tool_a", {}, "hello")
    assert result == "HELLO"


@pytest.mark.asyncio
async def test_call_order_is_forward():
    """Calls go M1 -> M2 (forward)."""

    class TagMiddleware:
        def __init__(self, tag: str):
            self.tag = tag

        async def intercept_call(self, tool_name: str, args: dict) -> dict:
            order = args.get("call_order", [])
            order.append(self.tag)
            args["call_order"] = order
            return args

        async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
            return result

    from typing import Any

    chain = MiddlewareChain([TagMiddleware("M1"), TagMiddleware("M2")])
    result = await chain.run_call("tool_a", {})
    assert result["call_order"] == ["M1", "M2"]


@pytest.mark.asyncio
async def test_result_order_is_reversed():
    """Results go M2 -> M1 (reversed)."""

    class TagResultMiddleware:
        def __init__(self, tag: str):
            self.tag = tag

        async def intercept_call(self, tool_name: str, args: dict) -> dict:
            return args

        async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
            order = result if isinstance(result, list) else [result]
            order.append(self.tag)
            return order

    from typing import Any

    chain = MiddlewareChain([TagResultMiddleware("M1"), TagResultMiddleware("M2")])
    result = await chain.run_result("tool_a", {}, [])
    assert result == ["M2", "M1"]


# ---------------------------------------------------------------------------
# LoggingMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logging_middleware_captures_call():
    lm = LoggingMiddleware()
    await lm.intercept_call("read_file", {"path": "/tmp/x"})
    assert len(lm.log) == 1
    assert lm.log[0]["phase"] == "call"
    assert lm.log[0]["tool_name"] == "read_file"
    assert lm.log[0]["args"] == {"path": "/tmp/x"}


@pytest.mark.asyncio
async def test_logging_middleware_captures_result():
    lm = LoggingMiddleware()
    await lm.intercept_result("read_file", {"path": "/tmp/x"}, "file content")
    assert len(lm.log) == 1
    assert lm.log[0]["phase"] == "result"
    assert lm.log[0]["tool_name"] == "read_file"
    assert lm.log[0]["result"] == "file content"


@pytest.mark.asyncio
async def test_logging_middleware_does_not_modify_args():
    lm = LoggingMiddleware()
    args = {"x": 1}
    result = await lm.intercept_call("tool_a", args)
    assert result is args


@pytest.mark.asyncio
async def test_logging_middleware_does_not_modify_result():
    lm = LoggingMiddleware()
    original = "result_value"
    result = await lm.intercept_result("tool_a", {}, original)
    assert result is original


# ---------------------------------------------------------------------------
# IdentityMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identity_middleware_transparent_call():
    im = IdentityMiddleware()
    args = {"x": 1, "y": "hello"}
    result = await im.intercept_call("tool_a", args)
    assert result == args


@pytest.mark.asyncio
async def test_identity_middleware_transparent_result():
    im = IdentityMiddleware()
    result = await im.intercept_result("tool_a", {}, 42)
    assert result == 42


# ---------------------------------------------------------------------------
# ToolMiddleware protocol check
# ---------------------------------------------------------------------------


def test_identity_middleware_satisfies_protocol():
    assert isinstance(IdentityMiddleware(), ToolMiddleware)


def test_logging_middleware_satisfies_protocol():
    assert isinstance(LoggingMiddleware(), ToolMiddleware)
