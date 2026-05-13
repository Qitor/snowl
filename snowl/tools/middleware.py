"""Tool middleware protocol and composition chain.

Framework role:
- Defines ToolMiddleware protocol for intercepting tool calls and results.
- Provides MiddlewareChain for composing multiple middlewares with correct ordering.
- Ships built-in middlewares (LoggingMiddleware, IdentityMiddleware) for common use cases.

Runtime/usage wiring:
- Wired into ReActAgent._execute_tool_call via the middlewares field.
- Future middleware implementations: EmulatedToolWrapper, StatefulToolExecutor, InjectionMiddleware.

Change guardrails:
- ToolMiddleware protocol is a public contract; adding required methods is breaking.
- MiddlewareChain ordering semantics (forward calls, reverse results) must be preserved.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolMiddleware(Protocol):
    """Intercepts and optionally transforms tool calls and their results."""

    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        """Pre-process tool call arguments. Return modified args."""
        ...

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        """Post-process tool call result. Return modified result."""
        ...


class MiddlewareChain:
    """Composes multiple ToolMiddleware instances with forward-call / reverse-result ordering.

    Calls flow forward: M1.intercept_call -> M2.intercept_call -> ... -> tool execution
    Results flow backward: ... -> M2.intercept_result -> M1.intercept_result
    """

    def __init__(self, middlewares: list[Any] | None = None) -> None:
        self._middlewares: list[Any] = list(middlewares) if middlewares else []

    async def run_call(self, tool_name: str, args: dict) -> dict:
        """Forward pass through all middlewares' intercept_call."""
        current_args = args
        for mw in self._middlewares:
            current_args = await mw.intercept_call(tool_name, current_args)
        return current_args

    async def run_result(self, tool_name: str, args: dict, result: Any) -> Any:
        """Reverse pass through all middlewares' intercept_result."""
        current_result = result
        for mw in reversed(self._middlewares):
            current_result = await mw.intercept_result(tool_name, args, current_result)
        return current_result


class LoggingMiddleware:
    """Records all tool calls and results for inspection."""

    def __init__(self) -> None:
        self.log: list[dict[str, Any]] = []

    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        self.log.append({"phase": "call", "tool_name": tool_name, "args": dict(args)})
        return args

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        self.log.append({"phase": "result", "tool_name": tool_name, "args": dict(args), "result": result})
        return result


class IdentityMiddleware:
    """No-op middleware, useful for testing composition."""

    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        return args

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        return result
