"""Injection middleware — intercepts tool results to inject adversarial strings.

Framework role:
- Implements ToolMiddleware to simulate prompt injection attacks on agent tool calls.
- Used by AgentDojo paired evaluation to test agent robustness against injected
  adversarial content in tool outputs.
- Supports multiple injection strategies (append, prepend, replace_field) and
  per-tool targeting.

Runtime/usage wiring:
- Wired as a ToolMiddleware in the agent's middleware chain during attacked trials.
- Configured per-trial via ``middleware_config`` from the AgentDojo adapter.

Change guardrails:
- InjectionMiddleware contract is security-critical; changes affect safety evaluation results.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from snowl.tools.middleware import ToolMiddleware


@dataclass(frozen=True)
class InjectionStrategy:
    """Configuration for a single injection attack."""

    injection_string: str
    position: str = "append"       # "append" | "prepend" | "replace_field"
    target_field: str | None = None  # For dict results, which field to inject into
    target_tools: list[str] | None = None  # Only inject into these tool results; None = all


class InjectionMiddleware:
    """Intercepts tool results to inject adversarial strings for safety evaluation.

    This middleware is used in AgentDojo paired evaluation to test whether agents
    can be manipulated by adversarial content injected into tool outputs.

    Usage:
        middleware = InjectionMiddleware(
            injection_string="IGNORE PREVIOUS INSTRUCTIONS...",
            position="append",
        )
        # Add to agent's middleware chain
    """

    def __init__(
        self,
        *,
        injection_string: str = "",
        position: str = "append",
        target_field: str | None = None,
        target_tools: list[str] | None = None,
        strategies: list[InjectionStrategy] | None = None,
    ) -> None:
        if strategies:
            self._strategies = list(strategies)
        else:
            self._strategies = [
                InjectionStrategy(
                    injection_string=injection_string,
                    position=position,
                    target_field=target_field,
                    target_tools=target_tools,
                )
            ]

    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        """Pass through tool calls unchanged — injection only affects results."""
        return args

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        """Apply injection strategies to tool results."""
        for strategy in self._strategies:
            if not self._should_inject(tool_name, strategy):
                continue
            result = self._apply_injection(result, strategy)
        return result

    def _should_inject(self, tool_name: str, strategy: InjectionStrategy) -> bool:
        """Check if injection should be applied for this tool."""
        if strategy.target_tools is None:
            return True
        return tool_name in strategy.target_tools

    def _apply_injection(self, result: Any, strategy: InjectionStrategy) -> Any:
        """Apply a single injection strategy to a tool result."""
        if isinstance(result, dict):
            # Deep copy to avoid mutating shared state
            result = dict(result)
            if strategy.target_field and strategy.target_field in result:
                field_value = result[strategy.target_field]
                if isinstance(field_value, str):
                    result[strategy.target_field] = self._inject_string(field_value, strategy)
                else:
                    # Convert non-string field to string, then inject
                    result[strategy.target_field] = self._inject_string(str(field_value), strategy)
            elif strategy.target_field is None:
                # No target field specified; inject into a common field or the whole dict
                # Try "output" or "message" fields first, then inject into stringified result
                for key in ("output", "message", "content", "result", "body"):
                    if key in result and isinstance(result[key], str):
                        result[key] = self._inject_string(result[key], strategy)
                        return result
                # Fallback: add an injection key
                result["injection"] = strategy.injection_string
            return result
        elif isinstance(result, str):
            return self._inject_string(result, strategy)
        elif isinstance(result, list):
            # Inject into list by appending the injection string as an element
            return list(result) + [strategy.injection_string]
        return result

    def _inject_string(self, value: str, strategy: InjectionStrategy) -> str:
        """Apply string injection based on position strategy."""
        if strategy.position == "append":
            return value + "\n" + strategy.injection_string
        elif strategy.position == "prepend":
            return strategy.injection_string + "\n" + value
        elif strategy.position == "replace_field":
            return strategy.injection_string
        return value


def build_injection_middleware_from_config(config: dict[str, Any]) -> InjectionMiddleware:
    """Build an InjectionMiddleware from middleware_config dict.

    Expected config keys:
        injection_string: The adversarial string to inject.
        position: "append" | "prepend" | "replace_field" (default: "append")
        target_field: Optional dict field to inject into.
        target_tools: Optional list of tool names to target.
    """
    return InjectionMiddleware(
        injection_string=config.get("injection_string", ""),
        position=config.get("position", "append"),
        target_field=config.get("target_field"),
        target_tools=config.get("target_tools"),
    )
