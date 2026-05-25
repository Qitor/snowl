"""MCP server lifecycle manager for Snowl evaluations.

Framework role:
- Starts, discovers, and stops MCP servers declared via `MCPServerSpec`.
- Bridges MCP tool discovery results into the Snowl tool pipeline.

Runtime/usage wiring:
- Used by `prepare_trial_phase` / `finalize_trial_phase` in engine.py.
- ``mcp`` SDK is lazy-imported inside methods so the module loads
  without the SDK installed (graceful degradation).

Change guardrails:
- Must not import from `snowl.core` except for `MCPServerSpec` / validation.
- The ``mcp`` SDK is a soft dependency — all public methods handle ImportError.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from snowl.core.mcp import MCPServerSpec, validate_mcp_server_spec

logger = logging.getLogger(__name__)


class MCPServerManager:
    """Lifecycle manager for MCP servers declared in an evaluation.

    Usage::

        async with MCPServerManager(specs) as mgr:
            tools = await mgr.discover_tools()
            result = await mgr.call_tool("server", "tool_name", {"arg": "val"})
    """

    def __init__(self, specs: tuple[MCPServerSpec, ...] | list[MCPServerSpec]) -> None:
        self._specs = tuple(specs)
        # name -> ClientSession (or equivalent)
        self._sessions: dict[str, Any] = {}
        # name -> (read_stream, write_stream) for stdio
        self._streams: dict[str, tuple[Any, Any]] = {}
        # name -> subprocess.Process for stdio
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        """Start all declared MCP servers and establish sessions."""
        if not self._specs:
            return

        for spec in self._specs:
            validate_mcp_server_spec(spec)
            try:
                if spec.transport == "stdio":
                    await self._start_stdio(spec)
                else:
                    await self._start_remote(spec)
            except Exception:
                logger.exception("Failed to start MCP server '%s'", spec.name)
                raise

    async def _start_stdio(self, spec: MCPServerSpec) -> None:
        """Start a stdio MCP server and create a session."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise ImportError(
                "The 'mcp' package is required for MCP server support. "
                "Install it with: pip install 'mcp>=1.0'"
            ) from exc

        server_params = StdioServerParameters(
            command=spec.command,
            args=list(spec.args),
            env=spec.env or None,
        )

        read_stream, write_stream = await stdio_client(server_params)
        session = ClientSession(read_stream, write_stream)
        await session.initialize()

        self._sessions[spec.name] = session
        self._streams[spec.name] = (read_stream, write_stream)
        logger.info("MCP server '%s' started (stdio)", spec.name)

    async def _start_remote(self, spec: MCPServerSpec) -> None:
        """Start a remote (SSE / streamable-http) MCP server session."""
        try:
            from mcp import ClientSession
        except ImportError as exc:
            raise ImportError(
                "The 'mcp' package is required for MCP server support. "
                "Install it with: pip install 'mcp>=1.0'"
            ) from exc

        if spec.transport == "sse":
            try:
                from mcp.client.sse import sse_client
            except ImportError as exc:
                raise ImportError(
                    "The 'mcp' package is required for SSE MCP support. "
                    "Install it with: pip install 'mcp>=1.0'"
                ) from exc

            read_stream, write_stream = await sse_client(
                url=spec.url,
                headers=spec.headers or None,
            )
            session = ClientSession(read_stream, write_stream)
            await session.initialize()
            self._sessions[spec.name] = session
            self._streams[spec.name] = (read_stream, write_stream)
            logger.info("MCP server '%s' started (sse)", spec.name)

        elif spec.transport == "streamable-http":
            try:
                from mcp.client.streamable_http import streamablehttp_client
            except ImportError as exc:
                raise ImportError(
                    "The 'mcp' package (>=1.9) is required for streamable-http MCP support. "
                    "Install it with: pip install 'mcp>=1.9'"
                ) from exc

            read_stream, write_stream = await streamablehttp_client(
                url=spec.url,
                headers=spec.headers or None,
            )
            session = ClientSession(read_stream, write_stream)
            await session.initialize()
            self._sessions[spec.name] = session
            self._streams[spec.name] = (read_stream, write_stream)
            logger.info("MCP server '%s' started (streamable-http)", spec.name)

        else:
            raise NotImplementedError(
                f"MCP transport '{spec.transport}' is not yet supported. "
                f"Supported transports: stdio, sse, streamable-http"
            )

    async def stop_all(self) -> None:
        """Gracefully shut down all MCP server sessions and processes."""
        for name, session in list(self._sessions.items()):
            try:
                await session.close()
            except Exception as exc:
                logger.warning("Error closing MCP session '%s': %s", name, exc)
        self._sessions.clear()
        self._streams.clear()

        for name, proc in list(self._processes.items()):
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._processes.clear()
        logger.info("All MCP servers stopped")

    # ------------------------------------------------------------------
    # Tool discovery & invocation
    # ------------------------------------------------------------------

    async def discover_tools(self) -> list[dict[str, Any]]:
        """Call ``tools/list`` on all active sessions, return raw descriptors.

        Each descriptor dict has keys: ``server_name``, ``tool_name``,
        ``description``, ``input_schema``.
        """
        tools: list[dict[str, Any]] = []
        for name, session in self._sessions.items():
            try:
                result = await session.list_tools()
                for tool in result.tools:
                    tools.append({
                        "server_name": name,
                        "tool_name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema or {},
                    })
            except Exception:
                logger.exception("Failed to discover tools from MCP server '%s'", name)
        return tools

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Call a tool on a specific MCP server session."""
        session = self._sessions.get(server_name)
        if session is None:
            raise RuntimeError(f"MCP server '{server_name}' is not running")
        result = await session.call_tool(tool_name, arguments)
        return result

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "MCPServerManager":
        await self.start_all()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop_all()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def active_server_names(self) -> list[str]:
        """Names of currently running MCP servers."""
        return list(self._sessions.keys())

    @property
    def specs(self) -> tuple[MCPServerSpec, ...]:
        """The server specs this manager was created with."""
        return self._specs
