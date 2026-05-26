"""Tests for the approval system: policies, decisions, and ToolCall."""

import pytest

from snowl.core.approval import (
    ApprovalAction,
    ApprovalDecision,
    AutoApprove,
    AutoReject,
    CompositeApproval,
    HumanApproval,
    RegexApproval,
    ToolCall,
)


# ---------------------------------------------------------------------------
# ToolCall & ApprovalDecision
# ---------------------------------------------------------------------------

class TestToolCall:
    def test_creation(self):
        tc = ToolCall(tool_name="read_file", arguments={"path": "/tmp/x"})
        assert tc.tool_name == "read_file"
        assert tc.arguments["path"] == "/tmp/x"

    def test_default_arguments(self):
        tc = ToolCall(tool_name="noop")
        assert tc.arguments == {}


class TestApprovalDecision:
    def test_approved_property(self):
        d = ApprovalDecision(action=ApprovalAction.APPROVE)
        assert d.approved is True
        assert d.rejected is False

    def test_rejected_property(self):
        d = ApprovalDecision(action=ApprovalAction.REJECT, reason="nope")
        assert d.approved is False
        assert d.rejected is True
        assert d.reason == "nope"

    def test_escalate(self):
        d = ApprovalDecision(action=ApprovalAction.ESCALATE)
        assert d.approved is False
        assert d.rejected is False


# ---------------------------------------------------------------------------
# AutoApprove
# ---------------------------------------------------------------------------

class TestAutoApprove:
    @pytest.mark.asyncio
    async def test_approves_everything(self):
        policy = AutoApprove()
        tc = ToolCall(tool_name="dangerous_tool", arguments={"cmd": "rm -rf /"})
        decision = await policy.check(tc, None)
        assert decision.approved is True


# ---------------------------------------------------------------------------
# AutoReject
# ---------------------------------------------------------------------------

class TestAutoReject:
    @pytest.mark.asyncio
    async def test_rejects_everything(self):
        policy = AutoReject()
        tc = ToolCall(tool_name="safe_tool")
        decision = await policy.check(tc, None)
        assert decision.rejected is True
        assert decision.reason is not None


# ---------------------------------------------------------------------------
# RegexApproval
# ---------------------------------------------------------------------------

class TestRegexApproval:
    @pytest.mark.asyncio
    async def test_approves_when_no_restrictions(self):
        policy = RegexApproval()
        tc = ToolCall(tool_name="any_tool")
        decision = await policy.check(tc, None)
        assert decision.approved is True

    @pytest.mark.asyncio
    async def test_blocked_pattern_rejects(self):
        policy = RegexApproval(blocked_patterns=[r"rm_", r"delete_"])
        tc = ToolCall(tool_name="rm_file")
        decision = await policy.check(tc, None)
        assert decision.rejected is True

    @pytest.mark.asyncio
    async def test_blocked_does_not_affect_others(self):
        policy = RegexApproval(blocked_patterns=[r"rm_"])
        tc = ToolCall(tool_name="read_file")
        decision = await policy.check(tc, None)
        assert decision.approved is True

    @pytest.mark.asyncio
    async def test_allowed_pattern_approves(self):
        policy = RegexApproval(allowed_patterns=[r"^read_", r"^list_"])
        tc = ToolCall(tool_name="read_file")
        decision = await policy.check(tc, None)
        assert decision.approved is True

    @pytest.mark.asyncio
    async def test_allowed_pattern_rejects_non_matching(self):
        policy = RegexApproval(allowed_patterns=[r"^read_"])
        tc = ToolCall(tool_name="write_file")
        decision = await policy.check(tc, None)
        assert decision.rejected is True

    @pytest.mark.asyncio
    async def test_blocked_takes_precedence_over_allowed(self):
        policy = RegexApproval(
            allowed_patterns=[r".*_file"],
            blocked_patterns=[r"rm_"],
        )
        tc = ToolCall(tool_name="rm_file")
        decision = await policy.check(tc, None)
        assert decision.rejected is True


# ---------------------------------------------------------------------------
# CompositeApproval
# ---------------------------------------------------------------------------

class TestCompositeApproval:
    @pytest.mark.asyncio
    async def test_approves_when_all_approve(self):
        policy = CompositeApproval([AutoApprove(), AutoApprove()])
        tc = ToolCall(tool_name="any")
        decision = await policy.check(tc, None)
        assert decision.approved is True

    @pytest.mark.asyncio
    async def test_rejects_if_any_rejects(self):
        policy = CompositeApproval([AutoApprove(), AutoReject()])
        tc = ToolCall(tool_name="any")
        decision = await policy.check(tc, None)
        assert decision.rejected is True

    @pytest.mark.asyncio
    async def test_first_rejection_wins(self):
        policy = CompositeApproval([
            RegexApproval(blocked_patterns=[r"rm_"]),
            AutoReject(),
        ])
        tc = ToolCall(tool_name="rm_file")
        decision = await policy.check(tc, None)
        assert decision.rejected is True
        assert "blocked" in decision.reason

    @pytest.mark.asyncio
    async def test_escalation_wins_over_approve(self):
        class EscalatePolicy:
            async def check(self, tool_call, context):
                return ApprovalDecision(action=ApprovalAction.ESCALATE, reason="needs review")

        policy = CompositeApproval([AutoApprove(), EscalatePolicy()])
        tc = ToolCall(tool_name="any")
        decision = await policy.check(tc, None)
        assert decision.action == ApprovalAction.ESCALATE

    @pytest.mark.asyncio
    async def test_empty_composite_approves(self):
        policy = CompositeApproval([])
        tc = ToolCall(tool_name="any")
        decision = await policy.check(tc, None)
        assert decision.approved is True


# ---------------------------------------------------------------------------
# HumanApproval
# ---------------------------------------------------------------------------

class TestHumanApproval:
    @pytest.mark.asyncio
    async def test_rejects_when_not_tty(self):
        policy = HumanApproval()
        tc = ToolCall(tool_name="any")
        # stdin.isatty() will return False in test environment
        decision = await policy.check(tc, None)
        assert decision.rejected is True
        assert "TTY" in decision.reason
