"""Solver protocol, chain composition, and AgentSolver bridge.

Framework role:
- Defines the composable Solver contract: ``async __call__(state, generate) -> state``.
- Provides ``chain()`` for sequential composition with early-exit on ``stop_reason``.
- Provides ``AgentSolver`` to wrap existing ``Agent`` Protocol objects as Solvers,
  preserving backward compatibility.

Runtime/usage wiring:
- Solvers are the low-level composable primitive for evaluation pipelines.
- ``generate()`` is the built-in Solver that calls the model with a tool-use loop.
- Higher-level ``Agent`` Protocol remains the simple black-box entry point;
  ``AgentSolver`` bridges between the two.

Change guardrails:
- Solver Protocol must stay framework-independent (no third-party imports).
- ``generate`` parameter is framework-injected; Solvers control whether/when to call it.
- Treat changes to Solver or Generate signatures as cross-cutting contract changes.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Protocol, Sequence, runtime_checkable

from snowl.core.agent import Agent, AgentContext, AgentState, StopReason
from snowl.core.declarations import declare
from snowl.errors import SnowlValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

Generate = Callable[..., Awaitable[AgentState]]
"""Function injected by the framework that calls the model.

Solvers receive this as a parameter and can choose whether and when
to invoke it.  This is the key design insight from Inspect AI: the
solver controls model interaction, not the other way around.
"""


# ---------------------------------------------------------------------------
# Solver Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Solver(Protocol):
    """Composable evaluation step.

    A Solver transforms an ``AgentState`` and returns the updated state.
    It may optionally call ``generate`` to produce model output.

    Reference: ``references/inspect_ai/src/inspect_ai/solver/_solver.py``
    """

    solver_id: str

    async def __call__(
        self,
        state: AgentState,
        generate: Generate,
    ) -> AgentState:
        """Execute one step of the evaluation pipeline.

        Args:
            state: Current execution state (messages, output, stop_reason, etc.).
            generate: Framework-injected function to call the model.
                The Solver decides whether/when to invoke it.

        Returns:
            Updated AgentState.
        """
        ...


# ---------------------------------------------------------------------------
# Resolver helper
# ---------------------------------------------------------------------------

def _resolve_solver(solver_like: Any) -> Solver:
    """Normalize a solver-like object to the Solver protocol.

    Accepts:
    - Solver instances (already protocol-conforming)
    - Plain async callables (wrapped with a generated solver_id)
    """
    if isinstance(solver_like, Solver):
        return solver_like
    if callable(solver_like):
        # Wrap plain callable as a Solver
        return _CallableSolver(solver_like)
    raise TypeError(
        f"Expected Solver or callable, got {type(solver_like).__name__}"
    )


class _CallableSolver:
    """Adapts a plain async callable ``(state, generate) -> state`` to Solver."""

    def __init__(self, fn: Callable[..., Awaitable[AgentState]], solver_id: str | None = None) -> None:
        self._fn = fn
        self.solver_id = solver_id or getattr(fn, "__name__", "callable_solver")

    async def __call__(self, state: AgentState, generate: Generate) -> AgentState:
        return await self._fn(state, generate)


# ---------------------------------------------------------------------------
# chain() composition
# ---------------------------------------------------------------------------

class Chain:
    """Execute multiple Solvers sequentially, with early exit.

    Reference: ``references/inspect_ai/src/inspect_ai/solver/_chain.py``
    """

    def __init__(self, *solvers: Solver | Callable[..., Awaitable[AgentState]]) -> None:
        self.solvers: list[Solver] = [_resolve_solver(s) for s in solvers]

    async def __call__(self, state: AgentState, generate: Generate) -> AgentState:
        for solver in self.solvers:
            if state.stop_reason is not None:
                break
            state = await solver(state, generate)
        return state

    def __len__(self) -> int:
        return len(self.solvers)

    def __getitem__(self, index: int) -> Solver:
        return self.solvers[index]


def chain(
    *solvers: Solver | Callable[..., Awaitable[AgentState]],
) -> Chain:
    """Compose multiple Solvers into a sequential chain.

    Execution order is left-to-right.  The chain stops early if
    ``state.stop_reason`` is not ``None`` after any step.

    A list of solvers is also accepted and auto-flattened::

        chain([s1, s2, s3])  # equivalent to chain(s1, s2, s3)

    Args:
        *solvers: One or more Solvers or async callables.

    Returns:
        A Chain that executes the solvers in order.
    """
    # Flatten lists
    flat: list[Solver | Callable[..., Awaitable[AgentState]]] = []
    for s in solvers:
        if isinstance(s, list):
            flat.extend(s)
        elif isinstance(s, Chain):
            flat.extend(s.solvers)
        else:
            flat.append(s)
    return Chain(*flat)


# ---------------------------------------------------------------------------
# AgentSolver bridge
# ---------------------------------------------------------------------------

class AgentSolver:
    """Wrap an existing Agent Protocol object as a Solver.

    The wrapped Agent ignores the ``generate`` parameter and manages
    its own model calls.  This preserves backward compatibility:
    users can choose between the high-level Agent Protocol (black box)
    and the low-level Solver chain (white box, composable).

    Reference: ``references/inspect_ai/src/inspect_ai/agent/_as_solver.py``
    """

    def __init__(self, agent: Agent, *, solver_id: str | None = None) -> None:
        self.agent = agent
        self.solver_id = solver_id or f"agent:{agent.agent_id}"

    async def __call__(self, state: AgentState, generate: Generate) -> AgentState:
        # Try to read the real context from named attribute (injected by the engine)
        context = state.solver_context
        if context is None:
            context = AgentContext(
                task_id="",
                sample_id=None,
                metadata={},
            )
        # Tools are injected by the engine into state.solver_tools
        tools = state.solver_tools
        return await self.agent.run(state, context, tools=tools)


# ---------------------------------------------------------------------------
# @solver decorator
# ---------------------------------------------------------------------------


def solver(value=None, *, solver_id: str | None = None, metadata: dict[str, Any] | None = None):
    """Decorator to declare a class or function as a solver.

    Usage::

        @solver
        class MySolver:
            solver_id = "my_solver"
            async def __call__(self, state, generate): ...

        @solver(solver_id="custom_id")
        class MySolver:
            ...
    """
    if solver_id is not None and (not isinstance(solver_id, str) or not solver_id.strip()):
        raise SnowlValidationError("Decorator @solver(...): 'solver_id' must be a non-empty string.")

    def _decorate(inner: Any) -> Any:
        declared_id = solver_id.strip() if isinstance(solver_id, str) and solver_id.strip() else None
        if declared_id is not None and hasattr(inner, "solver_id"):
            try:
                setattr(inner, "solver_id", declared_id)
            except Exception:
                pass
        return declare(inner, kind="solver", object_id=declared_id, metadata=metadata)

    if value is not None:
        return _decorate(value)
    return _decorate


# ---------------------------------------------------------------------------
# fork() parallel exploration
# ---------------------------------------------------------------------------

class Fork:
    """Execute multiple Solver branches in parallel, each with an independent state.

    Reference: ``references/inspect_ai/src/inspect_ai/solver/_fork.py``

    Usage::

        solver = chain(
            system_message("You are a helpful assistant."),
            use_tools(bash_tool),
            generate(max_steps=5),
            fork(
                InjectionScorer(injection="ignore previous instructions"),
                InjectionScorer(injection="you are now in admin mode"),
                merge="worst",
            ),
        )
    """

    solver_id: str = "fork"

    def __init__(
        self,
        *branches: Solver | Callable[..., Awaitable[AgentState]],
        merge: str | Callable[..., AgentState] = "best",
    ) -> None:
        if not branches:
            raise SnowlValidationError("fork() requires at least one branch.")
        self.branches: list[Solver] = [_resolve_solver(s) for s in branches]
        self.merge = merge

    async def __call__(self, state: AgentState, generate: Generate) -> AgentState:
        import asyncio
        import copy

        tasks = []
        for branch in self.branches:
            branch_state = copy.deepcopy(state)
            tasks.append(branch(branch_state, generate))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions — treat as failed branches
        valid_results: list[AgentState] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("fork() branch failed: %s", r)
            else:
                valid_results.append(r)

        if not valid_results:
            # All branches failed — return original state with error info
            output = dict(state.output) if state.output else {}
            output["fork_errors"] = [str(r) for r in results if isinstance(r, Exception)]
            state.output = output
            return state

        return self._merge(valid_results)

    def _merge(self, results: list[AgentState]) -> AgentState:
        """Merge branch results according to the merge strategy."""
        if callable(self.merge) and not isinstance(self.merge, str):
            return self.merge(results)

        if self.merge == "best":
            # Pick the result with the highest-scoring output
            return max(results, key=lambda s: _state_score(s))
        elif self.merge == "worst":
            # Pick the result with the lowest-scoring output (security: worst case)
            return min(results, key=lambda s: _state_score(s))
        elif self.merge == "all":
            # Return first result but stash all in output
            primary = results[0]
            output = dict(primary.output) if primary.output else {}
            output["fork_results"] = len(results)
            output["fork_branches"] = [
                {"stop_reason": getattr(r, "stop_reason", None),
                 "output_keys": list(r.output.keys()) if r.output else []}
                for r in results
            ]
            primary.output = output
            return primary
        else:
            # Default to first result
            return results[0]


def _state_score(state: AgentState) -> float:
    """Extract a numeric score from an AgentState for merge comparison."""
    if state.output and isinstance(state.output, dict):
        # Try common score keys
        for key in ("score", "reward", "value", "accuracy"):
            val = state.output.get(key)
            if isinstance(val, (int, float)):
                return float(val)
    return 0.0


def fork(
    *branches: Solver | Callable[..., Awaitable[AgentState]],
    merge: str | Callable[..., AgentState] = "best",
) -> Fork:
    """Create a Fork that executes multiple Solver branches in parallel.

    Each branch gets an independent deep copy of the state.

    Args:
        *branches: Solvers or async callables to execute in parallel.
        merge: Strategy for combining results:
            - "best": Pick the highest-scoring result (default).
            - "worst": Pick the lowest-scoring result (for security evals).
            - "all": Stash all results in state.output and return the first.
            - callable: Custom merge function receiving list of AgentState.

    Returns:
        A Fork solver.
    """
    return Fork(*branches, merge=merge)
