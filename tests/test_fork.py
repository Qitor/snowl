"""Tests for fork() parallel exploration with merge strategies."""

import asyncio
import pytest

from snowl.core.agent import AgentState, StopReason
from snowl.core.solver import Fork, Solver, _resolve_solver, fork
from snowl.errors import SnowlValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _passthrough(state: AgentState, generate) -> AgentState:
    """Solver that returns state unchanged."""
    return state


async def _set_output(key: str, value: float):
    """Factory: solver that sets state.output[key] = value."""
    async def _solver(state: AgentState, generate) -> AgentState:
        output = dict(state.output) if state.output else {}
        output[key] = value
        state.output = output
        return state
    return _solver


class _BranchSolver:
    """Solver that sets a specific score in output."""

    def __init__(self, score: float, solver_id: str = "branch"):
        self.scorer_id = solver_id
        self.solver_id = solver_id
        self._score = score

    async def __call__(self, state: AgentState, generate) -> AgentState:
        output = dict(state.output) if state.output else {}
        output["score"] = self._score
        state.output = output
        return state


class _FailingSolver:
    """Solver that raises an exception."""

    solver_id = "failing"

    async def __call__(self, state: AgentState, generate) -> AgentState:
        raise RuntimeError("branch failed")


# ---------------------------------------------------------------------------
# Fork construction
# ---------------------------------------------------------------------------

class TestForkConstruction:
    def test_requires_at_least_one_branch(self):
        with pytest.raises(SnowlValidationError, match="at least one"):
            Fork()

    def test_solver_id(self):
        f = Fork(_BranchSolver(1.0))
        assert f.solver_id == "fork"

    def test_branches_resolved(self):
        f = Fork(_BranchSolver(1.0), _passthrough)
        assert len(f.branches) == 2

    def test_merge_default(self):
        f = Fork(_BranchSolver(1.0))
        assert f.merge == "best"


# ---------------------------------------------------------------------------
# fork() convenience function
# ---------------------------------------------------------------------------

class TestForkFunction:
    def test_creates_fork(self):
        f = fork(_BranchSolver(1.0), merge="worst")
        assert isinstance(f, Fork)
        assert f.merge == "worst"


# ---------------------------------------------------------------------------
# Fork execution
# ---------------------------------------------------------------------------

class TestForkExecution:
    @pytest.mark.asyncio
    async def test_best_merge(self):
        f = Fork(
            _BranchSolver(0.5),
            _BranchSolver(1.0),
            _BranchSolver(0.0),
            merge="best",
        )
        state = AgentState(messages=[])
        result = await f(state, _noop_generate)
        assert result.output["score"] == 1.0

    @pytest.mark.asyncio
    async def test_worst_merge(self):
        f = Fork(
            _BranchSolver(0.5),
            _BranchSolver(1.0),
            _BranchSolver(0.0),
            merge="worst",
        )
        state = AgentState(messages=[])
        result = await f(state, _noop_generate)
        assert result.output["score"] == 0.0

    @pytest.mark.asyncio
    async def test_all_merge(self):
        f = Fork(
            _BranchSolver(0.5),
            _BranchSolver(1.0),
            merge="all",
        )
        state = AgentState(messages=[])
        result = await f(state, _noop_generate)
        assert result.output.get("fork_results") == 2

    @pytest.mark.asyncio
    async def test_custom_merge(self):
        def my_merge(results):
            # Return the last result
            return results[-1]

        f = Fork(
            _BranchSolver(1.0),
            _BranchSolver(0.0),
            merge=my_merge,
        )
        state = AgentState(messages=[])
        result = await f(state, _noop_generate)
        assert result.output["score"] == 0.0

    @pytest.mark.asyncio
    async def test_deep_copy_isolation(self):
        """Each branch should get its own copy of state."""
        call_count = 0

        class CounterSolver:
            solver_id = "counter"

            async def __call__(self, state: AgentState, generate) -> AgentState:
                nonlocal call_count
                call_count += 1
                output = dict(state.output) if state.output else {}
                output["count"] = call_count
                state.output = output
                return state

        f = Fork(CounterSolver(), CounterSolver(), merge="all")
        state = AgentState(messages=[], output={"original": True})
        result = await f(state, _noop_generate)

        # Original state should be unchanged
        assert state.output.get("original") is True
        assert "count" not in state.output

    @pytest.mark.asyncio
    async def test_branch_failure_handled(self):
        """If a branch fails, other branches should still produce results."""
        f = Fork(
            _FailingSolver(),
            _BranchSolver(0.8),
            merge="best",
        )
        state = AgentState(messages=[])
        result = await f(state, _noop_generate)
        assert result.output["score"] == 0.8

    @pytest.mark.asyncio
    async def test_all_branches_fail(self):
        """If all branches fail, return original state with error info."""
        f = Fork(
            _FailingSolver(),
            _FailingSolver(),
            merge="best",
        )
        state = AgentState(messages=[])
        result = await f(state, _noop_generate)
        assert "fork_errors" in result.output


async def _noop_generate(**kwargs):
    return AgentState(messages=[])
