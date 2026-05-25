"""Prompt-engineering Solvers: system_message, user_message, prompt_template.

Reference: ``references/inspect_ai/src/inspect_ai/solver/_prompt.py``
"""

from __future__ import annotations

from typing import Any, Mapping

from snowl.core.agent import AgentState
from snowl.core.solver import Generate, Solver


class SystemMessageSolver:
    """Inject a system message into the conversation.

    If the first message is already a system message, it is replaced.
    Otherwise, the system message is prepended.
    """

    solver_id: str = "system_message"

    def __init__(self, content: str) -> None:
        self.content = content

    async def __call__(self, state: AgentState, generate: Generate) -> AgentState:
        messages = list(state.messages)
        if messages and messages[0].get("role") == "system":
            messages[0] = {"role": "system", "content": self.content}
        else:
            messages.insert(0, {"role": "system", "content": self.content})
        state.messages = messages
        return state


def system_message(content: str) -> SystemMessageSolver:
    """Create a Solver that injects a system message.

    Args:
        content: The system message text.

    Returns:
        A Solver that prepends or replaces the system message.
    """
    return SystemMessageSolver(content)


class UserMessageSolver:
    """Append a user message to the conversation."""

    solver_id: str = "user_message"

    def __init__(self, content: str) -> None:
        self.content = content

    async def __call__(self, state: AgentState, generate: Generate) -> AgentState:
        messages = list(state.messages)
        messages.append({"role": "user", "content": self.content})
        state.messages = messages
        return state


def user_message(content: str) -> UserMessageSolver:
    """Create a Solver that appends a user message.

    Args:
        content: The user message text.

    Returns:
        A Solver that appends a user message.
    """
    return UserMessageSolver(content)


class PromptTemplateSolver:
    """Render a prompt template with variables from state metadata.

    Template uses ``{key}`` placeholders filled from ``state`` metadata
    or from explicit kwargs passed at construction time.
    """

    solver_id: str = "prompt_template"

    def __init__(self, template: str, **variables: Any) -> None:
        self.template = template
        self.variables = variables

    async def __call__(self, state: AgentState, generate: Generate) -> AgentState:
        # Merge: construction-time variables take precedence over metadata
        merged: dict[str, Any] = {}
        output_meta = state.output or {}
        if isinstance(output_meta, dict):
            merged.update(output_meta.get("metadata", {}))
        merged.update(self.variables)

        content = self.template.format(**merged)
        messages = list(state.messages)
        messages.append({"role": "user", "content": content})
        state.messages = messages
        return state


def prompt_template(template: str, **variables: Any) -> PromptTemplateSolver:
    """Create a Solver that renders a template as a user message.

    Args:
        template: A Python format string with ``{key}`` placeholders.
        **variables: Values to fill into the template.  Metadata from
            ``state.output["metadata"]`` is also available.

    Returns:
        A Solver that renders and appends the prompt.
    """
    return PromptTemplateSolver(template, **variables)
