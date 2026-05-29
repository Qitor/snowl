"""Bridge between ToolTracePolicyConfig and the Approval system.

Framework role:
- Adapts ToolTracePolicyConfig so that policy violations surface as
  ApprovalDecision.REJECT instead of raising PolicyViolationError.
- Allows composing tool-trace policies into the approval flow via
  CompositeApproval.

Runtime/usage wiring:
- Use PolicyApprovalAdapter when you want tool-trace policy violations
  to be routed through the approval system rather than hard-stopping
  execution.

Change guardrails:
- Must not modify ToolTracePolicyConfig or PolicyViolationError.
- Must stay compatible with the ApprovalPolicy protocol.
"""

from __future__ import annotations

from typing import Any

from snowl.core.approval import ApprovalAction, ApprovalDecision, ToolCall
from snowl.tools.policy_middleware import ToolTracePolicyConfig


class PolicyApprovalAdapter:
    """Adapts ToolTracePolicyConfig to the ApprovalPolicy protocol.

    When a tool call would violate the policy, returns REJECT instead
    of raising PolicyViolationError. This allows composing tool trace
    policies into the approval flow via CompositeApproval.

    Only checks call-time violations (forbidden tools, max calls,
    allowed args, arg value constraints, forbidden arg patterns).
    Return-value checks (blocked/expected return patterns) cannot be
    evaluated at approval time since the result is not yet available.
    """

    def __init__(self, config: ToolTracePolicyConfig) -> None:
        self._config = config

    @property
    def config(self) -> ToolTracePolicyConfig:
        return self._config

    async def check(self, tool_call: ToolCall, context: Any) -> ApprovalDecision:
        """Evaluate whether a tool call complies with the policy.

        Returns REJECT if the call would violate any call-time policy rule.
        Returns APPROVE if no violation is detected.
        """
        import re

        cfg = self._config
        tool_name = tool_call.tool_name
        args = tool_call.arguments

        # Forbidden tools
        if tool_name in cfg.forbidden_tools:
            return ApprovalDecision(
                action=ApprovalAction.REJECT,
                reason=f"Tool '{tool_name}' is forbidden by policy",
            )

        # Max calls — cannot fully enforce without call counter, but can check
        # if context carries existing call counts
        if cfg.max_calls is not None:
            existing = 0
            if hasattr(context, "metadata") and isinstance(context.metadata, dict):
                counts = context.metadata.get("__snowl_policy_call_counts", {})
                existing = sum(counts.values()) if isinstance(counts, dict) else 0
            if existing >= cfg.max_calls:
                return ApprovalDecision(
                    action=ApprovalAction.REJECT,
                    reason=f"Total tool calls ({existing}) would exceed limit ({cfg.max_calls})",
                )

        # Allowed args whitelist
        if tool_name in cfg.allowed_args:
            allowed = set(cfg.allowed_args[tool_name])
            for arg_name in args:
                if arg_name not in allowed:
                    return ApprovalDecision(
                        action=ApprovalAction.REJECT,
                        reason=f"Argument '{arg_name}' is not allowed for tool '{tool_name}'",
                    )

        # Arg value constraints
        if tool_name in cfg.arg_value_constraints:
            constraints = cfg.arg_value_constraints[tool_name]
            for arg_name, pattern in constraints.items():
                if arg_name in args:
                    value = str(args[arg_name])
                    if not re.search(pattern, value):
                        return ApprovalDecision(
                            action=ApprovalAction.REJECT,
                            reason=f"Argument '{arg_name}' value does not match constraint '{pattern}'",
                        )

        # Forbidden arg patterns (global)
        rendered = str(args)
        for pattern in cfg.forbidden_arg_patterns:
            if re.search(pattern, rendered):
                return ApprovalDecision(
                    action=ApprovalAction.REJECT,
                    reason=f"Arguments match forbidden pattern '{pattern}'",
                )

        return ApprovalDecision(action=ApprovalAction.APPROVE)
