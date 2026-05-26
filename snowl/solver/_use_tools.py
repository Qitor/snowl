"""use_tools() Solver: register tools into the solver state.

Reference: ``references/inspect_ai/src/inspect_ai/tool/_tool.py`` (use_tools)
"""

from __future__ import annotations

from typing import Any, Sequence

from snowl.core.agent import AgentState
from snowl.core.mcp import MCPServerSpec
from snowl.core.solver import Generate, Solver
from snowl.core.tool import ToolSpec, resolve_tool_spec
from snowl.tools.middleware import MiddlewareChain


class UseToolsSolver:
    """Register tools and optional middleware into the solver state.

    Tools are stored in ``state.output["_solver_tools"]`` as a list of ToolSpec.
    Middleware is stored in ``state.output["_solver_middleware"]``.
    The ``generate()`` Solver reads these when executing tool calls.
    """

    solver_id: str = "use_tools"

    def __init__(
        self,
        *tools: Any,
        middlewares: list[Any] | None = None,
        mcp_servers: tuple[MCPServerSpec, ...] | list[MCPServerSpec] | None = None,
    ) -> None:
        self._tool_specs: list[ToolSpec] = [resolve_tool_spec(t) for t in tools]
        self._middlewares = middlewares
        self._mcp_servers: tuple[MCPServerSpec, ...] = tuple(mcp_servers) if mcp_servers else ()

    def with_middleware(self, *middlewares: Any) -> "UseToolsSolver":
        """Return a copy of this solver with the given middleware added.

        This enables the fluent pattern::

            use_tools(bash_tool).with_middleware(LoggingMiddleware())
        """
        existing = list(self._middlewares or [])
        existing.extend(middlewares)
        return UseToolsSolver(
            *[t for t in self._tool_specs],
            middlewares=existing,
            mcp_servers=self._mcp_servers,
        )

    def with_mcp_servers(self, *specs: MCPServerSpec) -> "UseToolsSolver":
        """Return a copy with MCP server specs added.

        These are resolved to ToolSpecs at runtime when the engine
        starts the MCP servers and discovers their tools.

        Example::

            use_tools(bash_tool).with_mcp_servers(
                MCPServerSpec(name="fs", transport="stdio", command="mcp-fs"),
            )
        """
        existing = list(self._mcp_servers)
        existing.extend(specs)
        return UseToolsSolver(
            *[t for t in self._tool_specs],
            middlewares=self._middlewares,
            mcp_servers=tuple(existing),
        )

    async def __call__(self, state: AgentState, generate: Generate) -> AgentState:
        # Accumulate tools (don't overwrite existing ones)
        existing_specs: list[ToolSpec] = list(state.solver_tools or [])
        existing_names = {s.name for s in existing_specs}
        for spec in self._tool_specs:
            if spec.name not in existing_names:
                existing_specs.append(spec)
        state.solver_tools = existing_specs

        # Middleware
        if self._middlewares is not None:
            state.solver_middleware = list(self._middlewares)

        # MCP servers
        if self._mcp_servers:
            output = dict(state.output or {})
            output["_solver_mcp_servers"] = list(self._mcp_servers)
            state.output = output

        return state


def use_tools(
    *tools: Any,
    middlewares: list[Any] | None = None,
    mcp_servers: tuple[MCPServerSpec, ...] | list[MCPServerSpec] | None = None,
) -> UseToolsSolver:
    """Create a Solver that registers tools into the solver state.

    Args:
        *tools: ToolSpec objects, callables, or ToolLike objects.
        middlewares: Optional list of ToolMiddleware instances.
        mcp_servers: Optional MCP server specs to declare for runtime discovery.

    Returns:
        A Solver that registers the tools into ``state.output``.
    """
    return UseToolsSolver(*tools, middlewares=middlewares, mcp_servers=mcp_servers)
