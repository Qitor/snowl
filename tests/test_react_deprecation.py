"""Tests for ReActAgent deprecation warning."""

import warnings
import pytest

from snowl.core.agent import AgentContext, AgentState, StopReason
from snowl.core.task_result import Timing, Usage
from snowl.model.openai_compatible import ModelResponse
from snowl.agents.react_agent import ReActAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockModelClient:
    async def generate(self, messages, **kwargs):
        return ModelResponse(
            message={"role": "assistant", "content": "test response"},
            raw={},
            usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
            timing=Timing(started_at_ms=0, ended_at_ms=1, duration_ms=1),
        )


def _fresh_state() -> AgentState:
    return AgentState(messages=[], actions=[], observations=[], output=None, stop_reason=None)


def _make_context():
    return AgentContext(task_id="test", sample_id="s1", metadata={})


# ---------------------------------------------------------------------------
# ReActAgent deprecation
# ---------------------------------------------------------------------------

class TestReActAgentDeprecation:
    @pytest.mark.asyncio
    async def test_default_emits_deprecation_warning(self):
        agent = ReActAgent(model_client=MockModelClient())
        state = _fresh_state()
        state.messages.append({"role": "user", "content": "test"})
        context = _make_context()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await agent.run(state, context)
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "deprecated" in str(dep_warnings[0].message).lower()
            assert "_use_solver_chain" in str(dep_warnings[0].message)

    @pytest.mark.asyncio
    async def test_solver_chain_mode_no_deprecation_warning(self):
        agent = ReActAgent(model_client=MockModelClient(), _use_solver_chain=True)
        state = _fresh_state()
        state.messages.append({"role": "user", "content": "test"})
        context = _make_context()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await agent.run(state, context)
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            # Should not emit ReActAgent deprecation warning
            react_warnings = [x for x in dep_warnings if "_use_solver_chain" in str(x.message)]
            assert len(react_warnings) == 0
