"""submit_tool() Solver: add a submit/finish tool for the agent.

Reference: ``references/inspect_ai/src/inspect_ai/solver/_basic_agent.py``
(submit tool pattern where agent signals task completion)
"""

from __future__ import annotations

from typing import Any

from snowl.core.agent import AgentState
from snowl.core.solver import Generate, Solver
from snowl.core.tool import ToolSpec


def _submit_callable(answer: str) -> str:
    """Built-in submit tool: records the agent's final answer."""
    return answer


_SUBMIT_TOOL_SPEC = ToolSpec(
    name="submit",
    description="Submit your final answer to complete the task. Use this when you have finished.",
    parameters={
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "Your final answer to the task.",
            }
        },
        "required": ["answer"],
        "additionalProperties": False,
    },
    callable=_submit_callable,
)


class SubmitToolSolver:
    """Add a submit tool to the solver state so the agent can signal completion."""

    solver_id: str = "submit_tool"

    async def __call__(self, state: AgentState, generate: Generate) -> AgentState:
        output = dict(state.output or {})
        existing_specs: list[ToolSpec] = list(output.get("_solver_tools", []))
        existing_names = {s.name for s in existing_specs}
        if "submit" not in existing_names:
            existing_specs.append(_SUBMIT_TOOL_SPEC)
        output["_solver_tools"] = existing_specs
        state.output = output
        return state


def submit_tool() -> SubmitToolSolver:
    """Create a Solver that adds a submit tool.

    The submit tool lets the agent signal task completion with a final answer.

    Returns:
        A Solver that registers the submit tool.
    """
    return SubmitToolSolver()
