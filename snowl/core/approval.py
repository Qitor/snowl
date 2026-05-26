"""Approval system for gating tool execution in agent runs.

Framework role:
- Defines the approval policy protocol and decision types for controlling
  which tool calls an agent is allowed to execute.
- Provides built-in policies (auto-approve, auto-reject, human-approval,
  regex-based, composite) for common evaluation scenarios.

Runtime/usage wiring:
- Approval checks are inserted before tool execution in the runtime engine
  and in the ReAct agent loop.
- Policies are configured per-eval via project config or solver chain.

Change guardrails:
- Approval decisions must remain simple value objects; avoid I/O in decisions.
- Policy implementations may do I/O (human approval) but must be async.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, Sequence, runtime_checkable


class ApprovalAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class ToolCall:
    """Represents a tool call pending approval."""
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalDecision:
    """Result of an approval check."""
    action: ApprovalAction
    reason: str | None = None

    @property
    def approved(self) -> bool:
        return self.action == ApprovalAction.APPROVE

    @property
    def rejected(self) -> bool:
        return self.action == ApprovalAction.REJECT


@runtime_checkable
class ApprovalPolicy(Protocol):
    """Protocol for approval policies that gate tool execution."""

    async def check(self, tool_call: ToolCall, context: Any) -> ApprovalDecision:
        """Evaluate whether a tool call should be allowed.

        Args:
            tool_call: The tool call requesting approval.
            context: Agent context (AgentContext) providing task/sample metadata.

        Returns:
            An ApprovalDecision indicating whether to approve, reject, or escalate.
        """
        ...


# ---------------------------------------------------------------------------
# Built-in policies
# ---------------------------------------------------------------------------

class AutoApprove:
    """Policy that approves all tool calls."""

    async def check(self, tool_call: ToolCall, context: Any) -> ApprovalDecision:
        return ApprovalDecision(action=ApprovalAction.APPROVE)


class AutoReject:
    """Policy that rejects all tool calls."""

    async def check(self, tool_call: ToolCall, context: Any) -> ApprovalDecision:
        return ApprovalDecision(
            action=ApprovalAction.REJECT,
            reason="AutoReject: all tool calls are rejected",
        )


class RegexApproval:
    """Policy that approves tool calls matching name/argument patterns.

    If ``allowed_patterns`` is provided, tool names must match at least one
    pattern to be approved. If not provided, all names are allowed.
    If ``blocked_patterns`` is provided, matching names are rejected.
    """

    def __init__(
        self,
        allowed_patterns: Sequence[str] | None = None,
        blocked_patterns: Sequence[str] | None = None,
    ) -> None:
        self._allowed = [re.compile(p) for p in (allowed_patterns or [])]
        self._blocked = [re.compile(p) for p in (blocked_patterns or [])]

    async def check(self, tool_call: ToolCall, context: Any) -> ApprovalDecision:
        # Check blocked first
        for pat in self._blocked:
            if pat.search(tool_call.tool_name):
                return ApprovalDecision(
                    action=ApprovalAction.REJECT,
                    reason=f"RegexApproval: tool '{tool_call.tool_name}' blocked by pattern '{pat.pattern}'",
                )

        # If allow-list exists, name must match at least one
        if self._allowed:
            for pat in self._allowed:
                if pat.search(tool_call.tool_name):
                    return ApprovalDecision(action=ApprovalAction.APPROVE)
            return ApprovalDecision(
                action=ApprovalAction.REJECT,
                reason=f"RegexApproval: tool '{tool_call.tool_name}' not in allowed patterns",
            )

        return ApprovalDecision(action=ApprovalAction.APPROVE)


class CompositeApproval:
    """Policy that chains multiple policies. A call is approved only if all
    sub-policies approve. The first rejection or escalation wins.

    Escalation from any sub-policy causes the composite to escalate.
    """

    def __init__(self, policies: Sequence[ApprovalPolicy]) -> None:
        self._policies = list(policies)

    async def check(self, tool_call: ToolCall, context: Any) -> ApprovalDecision:
        for policy in self._policies:
            decision = await policy.check(tool_call, context)
            if decision.action == ApprovalAction.REJECT:
                return decision
            if decision.action == ApprovalAction.ESCALATE:
                return decision
        return ApprovalDecision(action=ApprovalAction.APPROVE)


class HumanApproval:
    """Policy that prompts a human for approval via stdin.

    Not suitable for automated CI — use only in interactive sessions.
    Falls back to reject if stdin is not a TTY.
    """

    async def check(self, tool_call: ToolCall, context: Any) -> ApprovalDecision:
        import sys

        if not sys.stdin.isatty():
            return ApprovalDecision(
                action=ApprovalAction.REJECT,
                reason="HumanApproval: stdin is not a TTY, auto-rejecting",
            )

        print(f"\n[APPROVAL REQUEST] Tool: {tool_call.tool_name}")
        print(f"  Arguments: {tool_call.arguments}")
        try:
            response = input("  Approve? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return ApprovalDecision(
                action=ApprovalAction.REJECT,
                reason="HumanApproval: input cancelled",
            )

        if response in ("y", "yes"):
            return ApprovalDecision(action=ApprovalAction.APPROVE)
        return ApprovalDecision(
            action=ApprovalAction.REJECT,
            reason="HumanApproval: user denied",
        )
