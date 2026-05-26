"""Tests for Solver + Engine integration: solver_chain on AgentVariant, AgentSolver context, and @solver decorator."""

import asyncio
import pytest

from snowl.core.agent import Agent, AgentContext, AgentState, StopReason
from snowl.core.agent_variant import AgentVariant, AgentVariantAdapter, bind_agent_variant
from snowl.core.solver import AgentSolver, Chain, Solver, chain, solver
from snowl.core.declarations import get_declaration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_state() -> AgentState:
    return AgentState(messages=[], actions=[], observations=[], output=None, stop_reason=None)


def _make_context(**overrides) -> AgentContext:
    defaults = dict(task_id="test_task", sample_id="s1", metadata={})
    defaults.update(overrides)
    return AgentContext(**defaults)


class _NoopSolver:
    solver_id = "noop"

    async def __call__(self, state: AgentState, generate) -> AgentState:
        state.stop_reason = StopReason.COMPLETED
        return state


class _SimpleAgent:
    agent_id = "simple"

    async def run(self, state, context, tools=None):
        state.stop_reason = StopReason.COMPLETED
        state.output = {"message": {"role": "assistant", "content": "done"}}
        return state


# ---------------------------------------------------------------------------
# AgentVariant solver_chain
# ---------------------------------------------------------------------------

class TestAgentVariantSolverChain:
    def test_variant_has_solver_chain_default_none(self):
        variant = AgentVariant(
            agent=_SimpleAgent(),
            agent_id="a",
            variant_id="v1",
        )
        assert variant.solver_chain is None

    def test_variant_with_solver_chain(self):
        solver_chain = chain(_NoopSolver())
        variant = AgentVariant(
            agent=_SimpleAgent(),
            agent_id="a",
            variant_id="v1",
            solver_chain=solver_chain,
        )
        assert variant.solver_chain is solver_chain

    def test_bind_propagates_solver_chain(self):
        solver_chain = chain(_NoopSolver())
        variant = AgentVariant(
            agent=_SimpleAgent(),
            agent_id="a",
            variant_id="v1",
            solver_chain=solver_chain,
        )
        adapter = bind_agent_variant(variant)
        assert adapter.solver_chain is solver_chain

    def test_bind_without_solver_chain(self):
        variant = AgentVariant(
            agent=_SimpleAgent(),
            agent_id="a",
            variant_id="v1",
        )
        adapter = bind_agent_variant(variant)
        assert adapter.solver_chain is None

    @pytest.mark.asyncio
    async def test_adapter_run_with_solver_chain(self):
        solver_chain = chain(_NoopSolver())
        variant = AgentVariant(
            agent=_SimpleAgent(),
            agent_id="a",
            variant_id="v1",
            solver_chain=solver_chain,
        )
        adapter = bind_agent_variant(variant)
        state = _fresh_state()
        context = _make_context()
        result = await adapter.run(state, context)
        # The solver chain should have set stop_reason
        assert result.stop_reason == StopReason.COMPLETED

    @pytest.mark.asyncio
    async def test_adapter_run_without_solver_chain(self):
        variant = AgentVariant(
            agent=_SimpleAgent(),
            agent_id="a",
            variant_id="v1",
        )
        adapter = bind_agent_variant(variant)
        state = _fresh_state()
        context = _make_context()
        result = await adapter.run(state, context)
        # The agent should have set output
        assert result.output["message"]["content"] == "done"


# ---------------------------------------------------------------------------
# AgentSolver context injection
# ---------------------------------------------------------------------------

class TestAgentSolverContext:
    @pytest.mark.asyncio
    async def test_reads_context_from_state(self):
        """AgentSolver should read context from state.solver_context."""
        context = _make_context(task_id="real_task", sample_id="s42")

        class _ContextCheckingAgent:
            agent_id = "checker"
            async def run(self, state, ctx, tools=None):
                # Verify we got the real context, not a stub
                state.output = {"task_id": ctx.task_id, "sample_id": ctx.sample_id}
                state.stop_reason = StopReason.COMPLETED
                return state

        bridge = AgentSolver(_ContextCheckingAgent())
        state = _fresh_state()
        state.solver_context = context

        result = await bridge(state, lambda **kw: None)
        assert result.output["task_id"] == "real_task"
        assert result.output["sample_id"] == "s42"

    @pytest.mark.asyncio
    async def test_falls_back_to_stub_context(self):
        """Without solver_context in state, AgentSolver creates a stub."""
        class _ContextAgent:
            agent_id = "ctx"
            async def run(self, state, ctx, tools=None):
                state.output = {"task_id": ctx.task_id}
                state.stop_reason = StopReason.COMPLETED
                return state

        bridge = AgentSolver(_ContextAgent())
        state = _fresh_state()
        result = await bridge(state, lambda **kw: None)
        assert result.output["task_id"] == ""

    @pytest.mark.asyncio
    async def test_reads_tools_from_state(self):
        """AgentSolver should read tools from state.solver_tools."""
        from snowl.core.tool import ToolSpec, build_tool_spec

        def my_tool(x: int) -> int:
            return x + 1

        spec = build_tool_spec(my_tool)

        class _ToolCheckingAgent:
            agent_id = "tool_checker"
            async def run(self, state, ctx, tools=None):
                tool_names = [t.name for t in tools] if tools else []
                state.output = {"tools": tool_names}
                state.stop_reason = StopReason.COMPLETED
                return state

        bridge = AgentSolver(_ToolCheckingAgent())
        state = _fresh_state()
        state.solver_tools = [spec]
        result = await bridge(state, lambda **kw: None)
        assert "my_tool" in result.output["tools"]


# ---------------------------------------------------------------------------
# @solver decorator
# ---------------------------------------------------------------------------

class TestSolverDecorator:
    def test_decorates_function(self):
        @solver
        def my_solver():
            pass

        decl = get_declaration(my_solver)
        assert decl is not None
        assert decl.kind == "solver"

    def test_decorates_with_id(self):
        @solver(solver_id="custom")
        class MySolver:
            solver_id = "original"

        decl = get_declaration(MySolver)
        assert decl is not None
        assert decl.object_id == "custom"

    def test_rejects_empty_id(self):
        from snowl.errors import SnowlValidationError
        with pytest.raises(SnowlValidationError, match="non-empty string"):
            @solver(solver_id="")
            def my_solver():
                pass

    def test_rejects_whitespace_id(self):
        from snowl.errors import SnowlValidationError
        with pytest.raises(SnowlValidationError, match="non-empty string"):
            @solver(solver_id="   ")
            def my_solver():
                pass
