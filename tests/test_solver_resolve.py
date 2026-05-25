"""Tests for declarative solver chain config resolution."""

import pytest

from snowl.core.agent import AgentState, StopReason
from snowl.core.solver import Chain
from snowl.solver.resolve import resolve_solver_chain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_state() -> AgentState:
    return AgentState(messages=[], actions=[], observations=[], output=None, stop_reason=None)


async def _noop_generate(**kwargs):
    return _fresh_state()


# ---------------------------------------------------------------------------
# resolve_solver_chain
# ---------------------------------------------------------------------------

class TestResolveSolverChain:
    def test_empty_config_returns_none(self):
        result = resolve_solver_chain({})
        assert result is None

    def test_no_steps_returns_none(self):
        result = resolve_solver_chain({"steps": []})
        assert result is None

    def test_system_message_step(self):
        config = {
            "steps": [{"system_message": {"content": "You are helpful."}}],
        }
        result = resolve_solver_chain(config)
        assert result is not None

    @pytest.mark.asyncio
    async def test_system_message_resolved_and_executable(self):
        config = {
            "steps": [{"system_message": {"content": "You are helpful."}}],
        }
        solver = resolve_solver_chain(config)
        state = _fresh_state()
        result = await solver(state, _noop_generate)
        assert result.messages[0]["role"] == "system"
        assert result.messages[0]["content"] == "You are helpful."

    def test_multiple_steps_returns_chain(self):
        config = {
            "steps": [
                {"system_message": {"content": "Hello"}},
                {"user_message": {"content": "World"}},
            ],
        }
        result = resolve_solver_chain(config)
        assert isinstance(result, Chain)
        assert len(result) == 2

    def test_shorthand_format(self):
        config = {
            "steps": ["system_message", "submit_tool"],
            "system_message": {"content": "Test"},
        }
        result = resolve_solver_chain(config)
        assert result is not None

    @pytest.mark.asyncio
    async def test_generate_step_with_model_client(self):
        """generate() step should resolve when model_client is provided."""
        from snowl.core.task_result import Timing, Usage
        from snowl.model.openai_compatible import ModelResponse

        class MockModelClient:
            async def generate(self, messages, **kwargs):
                return ModelResponse(
                    message={"role": "assistant", "content": "test"},
                    raw={},
                    usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
                    timing=Timing(started_at_ms=0, ended_at_ms=1, duration_ms=1),
                )

        config = {
            "steps": [
                {"system_message": {"content": "Hello"}},
                {"generate": {"max_steps": 1, "temperature": 0.0}},
            ],
        }
        result = resolve_solver_chain(config, model_client=MockModelClient())
        assert result is not None
        assert isinstance(result, Chain)
        assert len(result) == 2

    def test_generate_step_without_model_client_skipped(self):
        """generate() step should be skipped when no model_client is provided."""
        config = {
            "steps": [
                {"system_message": {"content": "Hello"}},
                {"generate": {"max_steps": 1}},
            ],
        }
        result = resolve_solver_chain(config)
        # Only system_message should be resolved; generate is skipped
        assert result is not None
        # Not a Chain since only one solver resolved
        assert not isinstance(result, Chain) or len(result) == 1

    def test_unknown_step_skipped(self):
        config = {
            "steps": [
                {"system_message": {"content": "Hello"}},
                {"unknown_solver": {}},
            ],
        }
        result = resolve_solver_chain(config)
        # Only system_message resolved
        assert result is not None
