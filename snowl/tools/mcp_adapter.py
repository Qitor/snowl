"""MCP tool to Snowl ToolSpec conversion.

Framework role:
- Converts MCP tool descriptors (from MCPServerManager.discover_tools)
  into Snowl ToolSpec instances whose callables route through the manager.
- MCP tool calls naturally flow through the existing MiddlewareChain because
  ToolSpec.callable returns are processed by GenerateSolver's tool execution path.

Runtime/usage wiring:
- Called by the engine's prepare_trial_phase after MCP server startup.
- Produces ToolSpec list that merges with project-declared tools.

Change guardrails:
- Must not import from snowl.runtime (boundary: tools ↔ runtime).
- The manager is typed as Any to avoid circular imports.
"""

from __future__ import annotations

import logging
from typing import Any

from snowl.core.tool import ToolSpec

logger = logging.getLogger(__name__)


def mcp_tool_to_spec(
    server_name: str,
    tool_name: str,
    description: str,
    input_schema: dict[str, Any],
    manager: Any,
) -> ToolSpec:
    """Convert an MCP tool descriptor into a Snowl ToolSpec.

    The callable wraps ``manager.call_tool(server_name, tool_name, args)``.

    Args:
        server_name: Name of the MCP server providing this tool.
        tool_name: Name of the tool within the server.
        description: Human-readable tool description.
        input_schema: JSON Schema for tool parameters.
        manager: MCPServerManager instance (typed as Any to avoid
            snowl.tools → snowl.runtime import cycle).

    Returns:
        A ToolSpec whose callable routes calls through the MCP manager.
    """
    # Build a closure that captures the routing information.
    async def _mcp_callable(**kwargs: Any) -> Any:
        return await manager.call_tool(server_name, tool_name, kwargs)

    # Normalize the input schema for ToolSpec consumption.
    parameters = dict(input_schema) if input_schema else {
        "type": "object",
        "properties": {},
    }
    parameters.setdefault("type", "object")
    parameters.setdefault("properties", {})

    return ToolSpec(
        name=tool_name,
        description=description or f"MCP tool '{tool_name}' from server '{server_name}'",
        parameters=parameters,
        callable=lambda **kwargs: None,  # Sync stub; async_callable is used
        async_callable=_mcp_callable,
        required_ops=(),
    )


async def discover_mcp_tool_specs(manager: Any) -> list[ToolSpec]:
    """Discover all tools from an MCPServerManager and convert to ToolSpec list.

    Args:
        manager: MCPServerManager instance (typed as Any to avoid boundary violation).

    Returns:
        List of ToolSpec instances for all discovered MCP tools.
    """
    raw_tools = await manager.discover_tools()
    specs: list[ToolSpec] = []

    for t in raw_tools:
        spec = mcp_tool_to_spec(
            server_name=t["server_name"],
            tool_name=t["tool_name"],
            description=t["description"],
            input_schema=t["input_schema"],
            manager=manager,
        )
        specs.append(spec)
        logger.debug(
            "Discovered MCP tool: %s (server=%s)",
            t["tool_name"],
            t["server_name"],
        )

    return specs
