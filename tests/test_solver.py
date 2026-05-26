"""Tests for the Solver protocol, chain composition, built-in solvers, and AgentSolver bridge."""

import asyncio
import pytest

from snowl.core.agent import Agent, AgentContext, AgentState, StopReason
from snowl.core.solver import (
    AgentSolver,
    Chain,
    Solver,
    _CallableSolver,
    _resolve_solver,
    chain,
)
from snowl.core.tool import ToolSpec
from snowl.solver import generate, prompt_template, submit_tool, system_message, use_tools, user_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _NoopSolver:
    """Solver that does nothing (identity)."""
    solver_id = "noop"

    async def __call__(self, state: AgentState, generate) -> AgentState:
        return state


async def _noop_generate(state: AgentState) -> AgentState:
    """A generate function that just marks the state as completed."""
    state.stop_reason = StopReason.COMPLETED
    return state


def _fresh_state() -> AgentState:
    return AgentState(messages=[], actions=[], observations=[], output=None, stop_reason=None)


# ---------------------------------------------------------------------------
# Solver Protocol
# ---------------------------------------------------------------------------

class TestSolverProtocol:
    def test_solver_is_runtime_checkable(self):
        noop = _NoopSolver()
        assert isinstance(noop, Solver)

    def test_callable_solver_adapter(self):
        async def my_solver(state: AgentState, generate) -> AgentState:
            return state

        adapted = _CallableSolver(my_solver, solver_id="my")
        assert adapted.solver_id == "my"
        assert isinstance(adapted, Solver)

    def test_resolve_solver_with_solver_instance(self):
        noop = _NoopSolver()
        resolved = _resolve_solver(noop)
        assert resolved is noop

    def test_resolve_solver_with_callable(self):
        async def my_solver(state: AgentState, generate) -> AgentState:
            return state

        resolved = _resolve_solver(my_solver)
        assert isinstance(resolved, _CallableSolver)
        assert resolved.solver_id == "my_solver"

    def test_resolve_solver_rejects_non_callable(self):
        with pytest.raises(TypeError, match="Expected Solver or callable"):
            _resolve_solver(42)


# ---------------------------------------------------------------------------
# chain() composition
# ---------------------------------------------------------------------------

class TestChain:
    @pytest.mark.asyncio
    async def test_chain_executes_in_order(self):
        order = []

        class SolverA:
            solver_id = "a"
            async def __call__(self, state: AgentState, generate) -> AgentState:
                order.append("a")
                return state

        class SolverB:
            solver_id = "b"
            async def __call__(self, state: AgentState, generate) -> AgentState:
                order.append("b")
                return state

        c = chain(SolverA(), SolverB())
        state = await c(_fresh_state(), _noop_generate)
        assert order == ["a", "b"]
        assert state.stop_reason is None

    @pytest.mark.asyncio
    async def test_chain_stops_on_stop_reason(self):
        class StopSolver:
            solver_id = "stop"
            async def __call__(self, state: AgentState, generate) -> AgentState:
                state.stop_reason = StopReason.COMPLETED
                return state

        class NeverReached:
            solver_id = "never"
            async def __call__(self, state: AgentState, generate) -> AgentState:
                pytest.fail("Should not be reached")

        c = chain(StopSolver(), NeverReached())
        state = await c(_fresh_state(), _noop_generate)
        assert state.stop_reason == StopReason.COMPLETED

    @pytest.mark.asyncio
    async def test_chain_flattens_list(self):
        order = []

        class Tagger:
            def __init__(self, tag: str):
                self.solver_id = tag
                self.tag = tag
            async def __call__(self, state: AgentState, generate) -> AgentState:
                order.append(self.tag)
                return state

        c = chain([Tagger("a"), Tagger("b")], Tagger("c"))
        await c(_fresh_state(), _noop_generate)
        assert order == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_chain_flattens_nested_chain(self):
        order = []

        class Tagger:
            def __init__(self, tag: str):
                self.solver_id = tag
                self.tag = tag
            async def __call__(self, state: AgentState, generate) -> AgentState:
                order.append(self.tag)
                return state

        inner = chain(Tagger("a"), Tagger("b"))
        outer = chain(inner, Tagger("c"))
        await outer(_fresh_state(), _noop_generate)
        assert order == ["a", "b", "c"]

    def test_chain_len_and_getitem(self):
        c = chain(_NoopSolver(), _NoopSolver(), _NoopSolver())
        assert len(c) == 3
        assert c[0].solver_id == "noop"


# ---------------------------------------------------------------------------
# Built-in Solvers
# ---------------------------------------------------------------------------

class TestSystemMessage:
    @pytest.mark.asyncio
    async def test_prepends_system_message(self):
        solver = system_message("You are a test assistant.")
        state = _fresh_state()
        state = await solver(state, _noop_generate)
        assert state.messages[0] == {"role": "system", "content": "You are a test assistant."}

    @pytest.mark.asyncio
    async def test_replaces_existing_system_message(self):
        solver = system_message("New system prompt")
        state = AgentState(
            messages=[{"role": "system", "content": "Old prompt"}],
            actions=[], observations=[], output=None, stop_reason=None,
        )
        state = await solver(state, _noop_generate)
        assert state.messages[0]["content"] == "New system prompt"
        assert len(state.messages) == 1


class TestUserMessage:
    @pytest.mark.asyncio
    async def test_appends_user_message(self):
        solver = user_message("Hello")
        state = _fresh_state()
        state = await solver(state, _noop_generate)
        assert state.messages[-1] == {"role": "user", "content": "Hello"}


class TestPromptTemplate:
    @pytest.mark.asyncio
    async def test_renders_template(self):
        solver = prompt_template("Hello {name}!", name="World")
        state = _fresh_state()
        state = await solver(state, _noop_generate)
        assert state.messages[-1]["content"] == "Hello World!"


class TestUseTools:
    @pytest.mark.asyncio
    async def test_registers_tools_in_state(self):
        def my_tool(x: int) -> int:
            return x + 1

        from snowl.core.tool import build_tool_spec
        spec = build_tool_spec(my_tool)

        solver = use_tools(spec)
        state = _fresh_state()
        state = await solver(state, _noop_generate)
        tools = state.solver_tools
        assert len(tools) == 1
        assert tools[0].name == "my_tool"

    @pytest.mark.asyncio
    async def test_with_middleware(self):
        def my_tool(x: int) -> int:
            return x + 1

        from snowl.core.tool import build_tool_spec
        from snowl.tools.middleware import LoggingMiddleware

        spec = build_tool_spec(my_tool)
        solver = use_tools(spec).with_middleware(LoggingMiddleware())
        state = _fresh_state()
        state = await solver(state, _noop_generate)
        assert state.solver_middleware is not None
        assert len(state.solver_middleware) == 1


class TestSubmitTool:
    @pytest.mark.asyncio
    async def test_adds_submit_tool(self):
        solver = submit_tool()
        state = _fresh_state()
        state = await solver(state, _noop_generate)
        tools = state.solver_tools
        assert any(t.name == "submit" for t in tools)


# ---------------------------------------------------------------------------
# AgentSolver bridge
# ---------------------------------------------------------------------------

class TestAgentSolver:
    @pytest.mark.asyncio
    async def test_wraps_agent_as_solver(self):
        class SimpleAgent:
            agent_id = "simple"

            async def run(self, state, context, tools=None):
                state.stop_reason = StopReason.COMPLETED
                state.output = {"message": {"role": "assistant", "content": "done"}}
                return state

        agent = SimpleAgent()
        wrapper = AgentSolver(agent)
        assert wrapper.solver_id == "agent:simple"
        assert isinstance(wrapper, Solver)

        state = await wrapper(_fresh_state(), _noop_generate)
        assert state.stop_reason == StopReason.COMPLETED
        assert state.output["message"]["content"] == "done"

    @pytest.mark.asyncio
    async def test_custom_solver_id(self):
        class MyAgent:
            agent_id = "my"
            async def run(self, state, context, tools=None):
                return state

        wrapper = AgentSolver(MyAgent(), solver_id="custom_id")
        assert wrapper.solver_id == "custom_id"
