"""Tests for EmulationScratchpad, EmulatedToolWrapper, prompt templates, and stub tools."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from snowl.core.tool import ToolSpec
from snowl.model.openai_compatible import ModelResponse
from snowl.tools.emulated_tool import (
    ADV_SIMULATOR_SYSTEM_PROMPT,
    ADV_SIMULATOR_USER_PROMPT,
    STUB_SENTINEL,
    STD_SIMULATOR_SYSTEM_PROMPT,
    STD_SIMULATOR_USER_PROMPT,
    EmulatedToolWrapper,
    EmulationScratchpad,
    make_stub_tool,
    render_toolkit_description,
)
from snowl.tools.middleware import LoggingMiddleware, MiddlewareChain, ToolMiddleware


# ---------------------------------------------------------------------------
# EmulationScratchpad
# ---------------------------------------------------------------------------


def test_scratchpad_empty_render():
    sp = EmulationScratchpad()
    assert sp.render() == ""


def test_scratchpad_single_entry():
    sp = EmulationScratchpad()
    sp.add("SearchEmail", '{"query": "test"}', '{"id": 1}', "Found 1 email")
    rendered = sp.render()
    assert "Action: SearchEmail" in rendered
    assert '{"query": "test"}' in rendered
    assert "Simulator Log Summary: Found 1 email" in rendered
    assert 'Observation: {"id": 1}' in rendered


def test_scratchpad_multiple_entries():
    sp = EmulationScratchpad()
    sp.add("SearchEmail", '{"query": "test"}', '{"id": 1}')
    sp.add("SendEmail", '{"to": "a@b.com"}', '{"ok": true}')
    rendered = sp.render()
    assert "Action: SearchEmail" in rendered
    assert "Action: SendEmail" in rendered


def test_scratchpad_render_without_thought():
    sp = EmulationScratchpad()
    sp.add("SearchEmail", '{"query": "test"}', '{"id": 1}', "Found email")
    rendered = sp.render(include_thought=False)
    assert "Simulator Log Summary" not in rendered
    assert 'Observation: {"id": 1}' in rendered


def test_scratchpad_render_last_step_only():
    sp = EmulationScratchpad()
    sp.add("SearchEmail", '{"query": "test"}', '{"id": 1}')
    sp.add("SendEmail", '{"to": "a@b.com"}', '{"ok": true}')
    rendered = sp.render(last_step_only=True)
    assert "Action: SearchEmail" not in rendered
    assert "Action: SendEmail" in rendered


def test_scratchpad_reset():
    sp = EmulationScratchpad()
    sp.add("SearchEmail", '{"query": "test"}', '{"id": 1}')
    sp.reset()
    assert len(sp.entries) == 0
    assert sp.render() == ""


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------


def test_std_prompt_contains_required_sections():
    assert "Tool Specifications" in STD_SIMULATOR_USER_PROMPT
    assert "Scratchpad" in STD_SIMULATOR_USER_PROMPT
    assert "Requirement Checklist" in STD_SIMULATOR_USER_PROMPT
    assert "Simulator Thought" in STD_SIMULATOR_USER_PROMPT
    assert "Observation" in STD_SIMULATOR_USER_PROMPT
    assert "{current_tool}" in STD_SIMULATOR_USER_PROMPT
    assert "{current_tool_description}" in STD_SIMULATOR_USER_PROMPT
    assert "{toolkit_descriptions}" in STD_SIMULATOR_USER_PROMPT
    assert "{input}" in STD_SIMULATOR_USER_PROMPT
    assert "{simulator_scratchpad}" in STD_SIMULATOR_USER_PROMPT


def test_adv_prompt_contains_stress_test():
    assert "Underspecifications" in ADV_SIMULATOR_USER_PROMPT
    assert "Stress Test" in ADV_SIMULATOR_USER_PROMPT
    assert "Never Compromise Realism" in ADV_SIMULATOR_USER_PROMPT
    assert "{underspecifications}" in ADV_SIMULATOR_USER_PROMPT
    assert "{risky_outcome}" in ADV_SIMULATOR_USER_PROMPT
    assert "{risky_actions}" in ADV_SIMULATOR_USER_PROMPT


def test_std_system_prompt_content():
    assert "Simulator" in STD_SIMULATOR_SYSTEM_PROMPT
    assert "realistic" in STD_SIMULATOR_SYSTEM_PROMPT.lower()


def test_adv_system_prompt_content():
    assert "stress test" in ADV_SIMULATOR_SYSTEM_PROMPT.lower()
    assert "Red-team" in ADV_SIMULATOR_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# render_toolkit_description
# ---------------------------------------------------------------------------


def test_render_toolkit_description():
    toolkit = {
        "toolkit": "Gmail",
        "name_for_model": "Gmail",
        "description_for_model": "Gmail email client",
        "tools": [
            {
                "name": "SendEmail",
                "summary": "Send an email",
                "parameters": [
                    {"name": "to", "type": "string", "description": "Recipient", "required": True}
                ],
                "returns": [{"name": "status", "type": "string", "description": "Send status"}],
                "exceptions": [],
            }
        ],
    }
    desc = render_toolkit_description(toolkit, detail_level="low")
    assert "Gmail" in desc
    assert "SendEmail" in desc
    assert "Send an email" in desc
    # Low detail should NOT include parameter specs
    assert "Arg to" not in desc


def test_render_toolkit_description_high_detail():
    toolkit = {
        "toolkit": "Gmail",
        "tools": [
            {
                "name": "SendEmail",
                "summary": "Send an email",
                "parameters": [
                    {"name": "to", "type": "string", "description": "Recipient", "required": True}
                ],
                "returns": [{"name": "status", "type": "string", "description": "Status"}],
                "exceptions": [{"name": "NotFoundException", "description": "Not found"}],
            }
        ],
    }
    desc = render_toolkit_description(toolkit, detail_level="high")
    assert "Arg to" in desc
    assert "Returns status" in desc
    assert "Exception NotFoundException" in desc


# ---------------------------------------------------------------------------
# Stub tools
# ---------------------------------------------------------------------------


def test_stub_tool_returns_sentinel():
    spec = make_stub_tool("test_tool", "A test", {"type": "object", "properties": {}})
    result = spec.callable()
    assert result == STUB_SENTINEL


def test_stub_tool_spec_has_correct_name_and_params():
    params = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    spec = make_stub_tool("echo", "Echo tool", params)
    assert spec.name == "echo"
    assert spec.description == "Echo tool"
    assert spec.parameters == params


# ---------------------------------------------------------------------------
# EmulatedToolWrapper
# ---------------------------------------------------------------------------


def _make_mock_client(response_text: str) -> AsyncMock:
    """Create a mock OpenAICompatibleChatClient that returns the given text."""
    from snowl.core.task_result import Timing, Usage

    mock = AsyncMock()
    mock.generate = AsyncMock(
        return_value=ModelResponse(
            message={"role": "assistant", "content": response_text},
            usage=Usage(input_tokens=10, output_tokens=20, total_tokens=30),
            timing=Timing(started_at_ms=0, ended_at_ms=100, duration_ms=100),
            raw={},
        )
    )
    mock.provider_id = "test_provider"
    mock.model = "test-model"
    mock.base_url = "http://test"
    return mock


@pytest.mark.asyncio
async def test_intercept_call_is_passthrough():
    client = _make_mock_client("Observation: {}")
    wrapper = EmulatedToolWrapper(emulator_client=client)
    args = {"x": 1}
    result = await wrapper.intercept_call("tool_a", args)
    assert result == args


@pytest.mark.asyncio
async def test_intercept_result_passes_through_non_sentinel():
    client = _make_mock_client("Observation: {}")
    wrapper = EmulatedToolWrapper(emulator_client=client)
    result = await wrapper.intercept_result("tool_a", {}, "normal_result")
    assert result == "normal_result"


@pytest.mark.asyncio
async def test_intercept_result_replaces_sentinel():
    response = "Simulator Log Summary: Email found.\nObservation: {\"id\": \"abc123\", \"subject\": \"Hello\"}"
    client = _make_mock_client(response)
    wrapper = EmulatedToolWrapper(emulator_client=client, user_input="find email", toolkit_descriptions="Gmail tools")
    result = await wrapper.intercept_result("SearchEmail", {"query": "test"}, STUB_SENTINEL)
    assert "abc123" in result


@pytest.mark.asyncio
async def test_parse_observation_well_formed():
    client = _make_mock_client("Observation: {}")
    wrapper = EmulatedToolWrapper(emulator_client=client)
    text = "Simulator Log Summary: Found email.\nObservation: {\"id\": 1}"
    obs, summary = wrapper._parse_observation(text)
    assert '"id": 1' in obs
    assert "Found email" in summary


@pytest.mark.asyncio
async def test_parse_observation_malformed():
    client = _make_mock_client("Observation: {}")
    wrapper = EmulatedToolWrapper(emulator_client=client)
    text = "This is just plain text without any markers."
    obs, summary = wrapper._parse_observation(text)
    assert obs == text
    assert summary == ""


@pytest.mark.asyncio
async def test_scratchpad_grows_with_each_call():
    response = "Simulator Log Summary: OK.\nObservation: {\"result\": true}"
    client = _make_mock_client(response)
    wrapper = EmulatedToolWrapper(emulator_client=client, user_input="test", toolkit_descriptions="tools")
    await wrapper.emulate_tool_call("Tool1", {"x": 1})
    assert len(wrapper.scratchpad.entries) == 1
    await wrapper.emulate_tool_call("Tool2", {"y": 2})
    assert len(wrapper.scratchpad.entries) == 2


@pytest.mark.asyncio
async def test_reset_clears_scratchpad():
    response = "Simulator Log Summary: OK.\nObservation: {}"
    client = _make_mock_client(response)
    wrapper = EmulatedToolWrapper(emulator_client=client, user_input="test", toolkit_descriptions="tools")
    await wrapper.emulate_tool_call("Tool1", {"x": 1})
    wrapper.reset()
    assert len(wrapper.scratchpad.entries) == 0
    assert wrapper.user_input is None
    assert wrapper.underspecifications is None


@pytest.mark.asyncio
async def test_emulate_with_mock_client():
    response = "Simulator Log Summary: Simulated email search.\nObservation: {\"emails\": [{\"id\": \"e1\", \"subject\": \"Meeting\"}]}"
    client = _make_mock_client(response)
    wrapper = EmulatedToolWrapper(emulator_client=client, user_input="find meeting email", toolkit_descriptions="Gmail tools")
    result = await wrapper.emulate_tool_call("SearchEmail", {"query": "meeting"})
    assert "e1" in result or "Meeting" in result


@pytest.mark.asyncio
async def test_emulate_with_critique():
    emulator_response = "Simulator Log Summary: Initial.\nObservation: {\"id\": \"abc\"}"
    critique_response = "Critique #1: Need more detail.\nRevised Simulator Log Summary #1: More detailed.\nRevised Observation #1: {\"id\": \"abc\", \"subject\": \"Hello World\"}"
    emulator_client = _make_mock_client(emulator_response)
    critiquer_client = _make_mock_client(critique_response)
    wrapper = EmulatedToolWrapper(
        emulator_client=emulator_client,
        critiquer_client=critiquer_client,
        num_critique_steps=1,
        user_input="test",
        toolkit_descriptions="tools",
    )
    result = await wrapper.emulate_tool_call("SearchEmail", {"query": "test"})
    assert "Hello World" in result or "abc" in result


@pytest.mark.asyncio
async def test_emit_fn_called():
    response = "Simulator Log Summary: OK.\nObservation: {}"
    client = _make_mock_client(response)
    emitted: list[dict[str, Any]] = []
    wrapper = EmulatedToolWrapper(
        emulator_client=client,
        emit_fn=lambda e: emitted.append(e),
        user_input="test",
        toolkit_descriptions="tools",
    )
    await wrapper.emulate_tool_call("Tool1", {"x": 1})
    assert len(emitted) == 1
    assert emitted[0]["event"] == "toolemu.emulation"
    assert emitted[0]["tool_name"] == "Tool1"


@pytest.mark.asyncio
async def test_provider_admission_acquired():
    response = "Simulator Log Summary: OK.\nObservation: {}"
    client = _make_mock_client(response)

    scheduler = MagicMock()
    scheduler.provider_admission = MagicMock()
    scheduler.provider_admission.return_value.__aenter__ = AsyncMock(return_value=None)
    scheduler.provider_admission.return_value.__aexit__ = AsyncMock(return_value=None)

    wrapper = EmulatedToolWrapper(
        emulator_client=client,
        scheduler=scheduler,
        user_input="test",
        toolkit_descriptions="tools",
    )
    await wrapper.emulate_tool_call("Tool1", {"x": 1})
    scheduler.provider_admission.assert_called_once_with("test_provider")


def test_wrapper_satisfies_tool_middleware_protocol():
    """EmulatedToolWrapper satisfies ToolMiddleware protocol."""
    client = _make_mock_client("Observation: {}")
    wrapper = EmulatedToolWrapper(emulator_client=client)
    assert isinstance(wrapper, ToolMiddleware)


@pytest.mark.asyncio
async def test_compose_with_logging_middleware():
    """EmulatedToolWrapper composed with LoggingMiddleware in MiddlewareChain."""
    response = "Simulator Log Summary: OK.\nObservation: {\"ok\": true}"
    client = _make_mock_client(response)
    lm = LoggingMiddleware()
    wrapper = EmulatedToolWrapper(emulator_client=client, user_input="test", toolkit_descriptions="tools")
    chain = MiddlewareChain([wrapper, lm])

    args = await chain.run_call("Tool1", {"x": 1})
    assert args == {"x": 1}

    result = await chain.run_result("Tool1", {"x": 1}, dict(STUB_SENTINEL))
    # The result should be the emulated observation, not the sentinel
    assert isinstance(result, str)
    # LoggingMiddleware should have captured both call and result
    assert len(lm.log) == 2


@pytest.mark.asyncio
async def test_multiple_sentinel_replacements():
    """Multiple sentinel replacements in sequence."""
    response = "Simulator Log Summary: Step result.\nObservation: {\"step\": true}"
    client = _make_mock_client(response)
    wrapper = EmulatedToolWrapper(emulator_client=client, user_input="test", toolkit_descriptions="tools")

    result1 = await wrapper.intercept_result("Tool1", {}, dict(STUB_SENTINEL))
    result2 = await wrapper.intercept_result("Tool2", {}, dict(STUB_SENTINEL))
    assert len(wrapper.scratchpad.entries) == 2


@pytest.mark.asyncio
async def test_adv_mode_builds_correct_messages():
    """Adversarial mode includes underspecifications etc. in prompt."""
    response = "Simulator Log Summary: OK.\nObservation: {}"
    client = _make_mock_client(response)
    wrapper = EmulatedToolWrapper(
        emulator_client=client,
        simulator_type="adv_thought",
        underspecifications={"Task Information": ["missing detail"]},
        risky_outcome="Data loss",
        risky_actions=["delete file"],
        user_input="clean folder",
        toolkit_descriptions="File tools",
    )
    messages = wrapper._build_emulation_messages("DeleteFile", {"path": "/tmp/x"})
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "stress test" in messages[0]["content"].lower()
    user_content = messages[1]["content"]
    assert "missing detail" in user_content
    assert "Data loss" in user_content
    assert "delete file" in user_content
