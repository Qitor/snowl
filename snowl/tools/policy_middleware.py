"""Runtime tool-trace policy enforcement middleware.

Framework role:
- Enforces tool-use policies at call time (forbidden tools, arg constraints, max calls)
  rather than only post-hoc scoring.
- Shares ToolTracePolicyConfig with ToolTracePolicyScorer so rules are defined once.

Runtime/usage wiring:
- Insert PolicyEnforcementMiddleware into a MiddlewareChain before agent tool execution.
- Raises PolicyViolationError on violation, halting the offending call.

Change guardrails:
- ToolTracePolicyConfig is shared between scorer and middleware; field changes affect both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from snowl.errors import PolicyViolationError


@dataclass(frozen=True)
class ToolTracePolicyConfig:
    """Shared policy configuration for both runtime enforcement and post-hoc scoring.

    v1 fields (shared with ToolTracePolicyScorer):
        required_tools: Tools that must be called at least once.
        forbidden_tools: Tools that must not be called.
        forbidden_arg_patterns: Regex patterns that must not appear in any tool-call arguments.
        max_calls: Maximum total tool calls allowed.

    v2 fields (runtime enforcement only):
        allowed_args: Per-tool whitelist of allowed argument names. Empty dict = no constraint.
        arg_value_constraints: Per-tool per-arg regex patterns that values must match.
            Inner dict maps arg name -> regex pattern.
        blocked_return_patterns: Per-tool regex patterns that must not appear in return values.
    """

    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    forbidden_arg_patterns: tuple[str, ...] = ()
    max_calls: int | None = None
    allowed_args: dict[str, tuple[str, ...]] = field(default_factory=dict)
    arg_value_constraints: dict[str, dict[str, str]] = field(default_factory=dict)
    blocked_return_patterns: dict[str, tuple[str, ...]] = field(default_factory=dict)


class PolicyEnforcementMiddleware:
    """Middleware that enforces ToolTracePolicyConfig at runtime.

    intercept_call: blocks forbidden tools, validates arg names/values, enforces max_calls.
    intercept_result: checks return values against blocked_return_patterns.
    """

    def __init__(self, config: ToolTracePolicyConfig) -> None:
        self._config = config
        self._call_counts: dict[str, int] = {}
        self._total_calls = 0

    @property
    def config(self) -> ToolTracePolicyConfig:
        return self._config

    @property
    def call_counts(self) -> dict[str, int]:
        return dict(self._call_counts)

    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        cfg = self._config

        # Forbidden tools
        if tool_name in cfg.forbidden_tools:
            raise PolicyViolationError(
                tool_name=tool_name,
                violation_type="forbidden_tool",
                detail=f"Tool '{tool_name}' is forbidden by policy",
            )

        # Max calls
        if cfg.max_calls is not None:
            if self._total_calls >= cfg.max_calls:
                raise PolicyViolationError(
                    tool_name=tool_name,
                    violation_type="max_calls_exceeded",
                    detail=f"Total tool calls ({self._total_calls}) exceed limit ({cfg.max_calls})",
                )

        # Allowed args whitelist
        if tool_name in cfg.allowed_args:
            allowed = set(cfg.allowed_args[tool_name])
            for arg_name in args:
                if arg_name not in allowed:
                    raise PolicyViolationError(
                        tool_name=tool_name,
                        violation_type="forbidden_arg",
                        detail=f"Argument '{arg_name}' is not allowed for tool '{tool_name}'",
                    )

        # Arg value constraints
        if tool_name in cfg.arg_value_constraints:
            constraints = cfg.arg_value_constraints[tool_name]
            for arg_name, pattern in constraints.items():
                if arg_name in args:
                    value = str(args[arg_name])
                    if not re.search(pattern, value):
                        raise PolicyViolationError(
                            tool_name=tool_name,
                            violation_type="arg_value_constraint",
                            detail=f"Argument '{arg_name}' value does not match constraint '{pattern}'",
                        )

        # Forbidden arg patterns (global)
        rendered = str(args)
        for pattern in cfg.forbidden_arg_patterns:
            if re.search(pattern, rendered):
                raise PolicyViolationError(
                    tool_name=tool_name,
                    violation_type="forbidden_arg_pattern",
                    detail=f"Arguments match forbidden pattern '{pattern}'",
                )

        # Track call
        self._call_counts[tool_name] = self._call_counts.get(tool_name, 0) + 1
        self._total_calls += 1

        return args

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        cfg = self._config

        # Blocked return patterns
        if tool_name in cfg.blocked_return_patterns:
            rendered = str(result)
            for pattern in cfg.blocked_return_patterns[tool_name]:
                if re.search(pattern, rendered):
                    raise PolicyViolationError(
                        tool_name=tool_name,
                        violation_type="blocked_return_pattern",
                        detail=f"Return value matches blocked pattern '{pattern}'",
                    )

        return result
