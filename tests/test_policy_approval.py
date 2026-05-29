"""Tests for PolicyApprovalAdapter — tool-trace-policy to approval-system bridge."""

from __future__ import annotations

import pytest

from snowl.core.approval import ApprovalAction, CompositeApproval, ToolCall
from snowl.tools.policy_approval import PolicyApprovalAdapter
from snowl.tools.policy_middleware import ToolTracePolicyConfig


def _call(tool: str, **kwargs) -> ToolCall:
    return ToolCall(tool_name=tool, arguments=kwargs)


@pytest.mark.asyncio
async def test_approves_when_no_violation():
    config = ToolTracePolicyConfig()
    adapter = PolicyApprovalAdapter(config)
    decision = await adapter.check(_call("read_file", path="/tmp/a"), context=None)
    assert decision.approved


@pytest.mark.asyncio
async def test_rejects_forbidden_tool():
    config = ToolTracePolicyConfig(forbidden_tools=("rm_rf",))
    adapter = PolicyApprovalAdapter(config)
    decision = await adapter.check(_call("rm_rf"), context=None)
    assert decision.rejected
    assert "forbidden" in (decision.reason or "").lower()


@pytest.mark.asyncio
async def test_rejects_disallowed_arg():
    config = ToolTracePolicyConfig(allowed_args={"read_file": ("path",)})
    adapter = PolicyApprovalAdapter(config)
    decision = await adapter.check(_call("read_file", path="/tmp/a", secret="key"), context=None)
    assert decision.rejected
    assert "secret" in (decision.reason or "")


@pytest.mark.asyncio
async def test_rejects_arg_value_constraint():
    config = ToolTracePolicyConfig(
        arg_value_constraints={"read_file": {"path": r"^/safe/"}}
    )
    adapter = PolicyApprovalAdapter(config)
    decision = await adapter.check(_call("read_file", path="/unsafe/file"), context=None)
    assert decision.rejected


@pytest.mark.asyncio
async def test_allows_matching_arg_value():
    config = ToolTracePolicyConfig(
        arg_value_constraints={"read_file": {"path": r"^/safe/"}}
    )
    adapter = PolicyApprovalAdapter(config)
    decision = await adapter.check(_call("read_file", path="/safe/file"), context=None)
    assert decision.approved


@pytest.mark.asyncio
async def test_rejects_forbidden_arg_pattern():
    config = ToolTracePolicyConfig(forbidden_arg_patterns=(r"password",))
    adapter = PolicyApprovalAdapter(config)
    decision = await adapter.check(_call("send_email", body="my password is x"), context=None)
    assert decision.rejected


@pytest.mark.asyncio
async def test_composite_with_policy_approval():
    """PolicyApprovalAdapter works inside CompositeApproval."""
    from snowl.core.approval import AutoApprove

    policy_config = ToolTracePolicyConfig(forbidden_tools=("dangerous_tool",))
    policy_adapter = PolicyApprovalAdapter(policy_config)
    composite = CompositeApproval([AutoApprove(), policy_adapter])

    # Safe tool passes
    decision = await composite.check(_call("safe_tool"), context=None)
    assert decision.approved

    # Forbidden tool rejected by policy adapter
    decision = await composite.check(_call("dangerous_tool"), context=None)
    assert decision.rejected


@pytest.mark.asyncio
async def test_expected_return_patterns_not_checked_at_approval_time():
    """Return patterns cannot be checked before execution — only at intercept_result time."""
    config = ToolTracePolicyConfig(
        expected_return_patterns={"read_file": (r"^OK",)}
    )
    adapter = PolicyApprovalAdapter(config)
    # Approval should pass (return value not yet available)
    decision = await adapter.check(_call("read_file", path="/tmp/a"), context=None)
    assert decision.approved
