"""Stateful tool execution via the ToolMiddleware protocol.

Framework role:
- Manages stateful tool environments for benchmarks like AgentDojo where tools
  mutate shared state (e.g., BankAccount, reservations) across calls.
- StatefulToolExecutor intercepts stub tool results and delegates to real
  Python implementations that read/write a state dict.

Runtime/usage wiring:
- StatefulToolExecutor is wired as a ToolMiddleware in ReActAgent or
  AgentDojoAgent, following the same sentinel pattern as EmulatedToolWrapper.
- Stub tools return {"__stateful__": True}; the executor replaces the sentinel
  with the result of the real tool function call.

Change guardrails:
- Benchmark-specific tool implementations live in snowl/benchmarks/agentdojo/tools.py.
- This module provides the generic StatefulToolExecutor middleware only.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from snowl.core.tool import ToolSpec
from snowl.tools.middleware import ToolMiddleware


STATEFUL_SENTINEL = {"__stateful__": True}


def make_stateful_stub_tool(name: str, description: str, parameters: dict[str, Any]) -> ToolSpec:
    """Create a ToolSpec whose callable returns the stateful sentinel value."""

    def _stub(**kwargs: Any) -> dict[str, Any]:
        return dict(STATEFUL_SENTINEL)

    return ToolSpec(
        name=name,
        description=description,
        parameters=parameters,
        callable=_stub,
    )


def _get_suite_tool_implementations(suite: str) -> dict[str, Callable]:
    """Lazy-load suite tool implementations from the benchmark package."""
    from snowl.benchmarks.agentdojo.tools import SUITE_TOOL_IMPLEMENTATIONS
    return SUITE_TOOL_IMPLEMENTATIONS.get(suite, {})


# Backward-compatible re-exports for external consumers
def __getattr__(name: str) -> Any:
    if name in ("BANKING_TOOLS", "TRAVEL_TOOLS", "SUITE_TOOL_IMPLEMENTATIONS"):
        from snowl.benchmarks.agentdojo import tools as _tools
        return getattr(_tools, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------------------
# StatefulToolExecutor
# ---------------------------------------------------------------------------


class StatefulToolExecutor:
    """ToolMiddleware that manages stateful tool execution.

    Intercepts stub tool results (sentinel ``{"__stateful__": True}``) and
    replaces them with the result of the real tool implementation, which
    reads and mutates the shared state dict.
    """

    def __init__(
        self,
        *,
        suite: str,
        tool_implementations: dict[str, Callable] | None = None,
        initial_state: dict[str, Any] | None = None,
        emit_fn: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.suite = suite
        self._tool_impls = tool_implementations or _get_suite_tool_implementations(suite)
        self._initial_state = copy.deepcopy(initial_state or {})
        self._state = copy.deepcopy(self._initial_state)
        self._pre_state = copy.deepcopy(self._initial_state)
        self.emit_fn = emit_fn

    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        return args

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        if isinstance(result, dict) and result.get("__stateful__"):
            return self._execute_tool(tool_name, args)
        return result

    def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        impl = self._tool_impls.get(tool_name)
        if impl is None:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            result = impl(self._state, **args)
        except Exception as exc:
            return {"error": f"Tool {tool_name} failed: {exc}"}

        if self.emit_fn is not None:
            self.emit_fn({
                "event": "agentdojo.stateful_execution",
                "tool_name": tool_name,
                "tool_args": args,
                "result": result,
                "suite": self.suite,
            })
        return result

    def get_pre_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._pre_state)

    def get_post_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._state)

    def get_state_diff(self) -> list[dict[str, Any]]:
        return _compute_state_diff(self._pre_state, self._state)

    def reset(self, initial_state: dict[str, Any] | None = None) -> None:
        if initial_state is not None:
            self._initial_state = copy.deepcopy(initial_state)
        self._state = copy.deepcopy(self._initial_state)
        self._pre_state = copy.deepcopy(self._initial_state)


# ---------------------------------------------------------------------------
# State diff computation
# ---------------------------------------------------------------------------


def _compute_state_diff(pre: dict[str, Any], post: dict[str, Any], prefix: str = "") -> list[dict[str, Any]]:
    """Compute state_checks compatible diff between pre and post states.

    Returns a list of dicts with keys: path, op, value
    - op "changed": value at path differs between pre and post
    - op "unchanged": value at path is the same
    - op "equals": post value equals the given value
    """
    checks: list[dict[str, Any]] = []
    all_keys = set(pre.keys()) | set(post.keys())
    for key in sorted(all_keys):
        path = f"{prefix}.{key}" if prefix else key
        pre_val = pre.get(key)
        post_val = post.get(key)
        if isinstance(pre_val, dict) and isinstance(post_val, dict):
            checks.extend(_compute_state_diff(pre_val, post_val, prefix=path))
        elif pre_val != post_val:
            checks.append({"path": path, "op": "changed", "value": post_val})
    return checks
