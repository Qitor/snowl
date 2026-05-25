"""Tests for MCP integration: ToolSpec conversion, solver chain, and engine wiring."""

import asyncio
import pytest

from snowl.core.mcp import MCPServerSpec
from snowl.core.tool import ToolSpec
from snowl.core.agent import AgentState
from snowl.solver._use_tools import UseToolsSolver, use_tools
from snowl.tools.mcp_adapter import mcp_tool_to_spec, discover_mcp_tool_specs


# ---------------------------------------------------------------------------
# MCP Tool → ToolSpec conversion
# ---------------------------------------------------------------------------

class TestMCPToolToSpec:
    def test_basic_conversion(self):
        """Verify MCP tool descriptor converts to ToolSpec with async_callable."""

        class FakeManager:
            async def call_tool(self, server, tool, args):
                return f"result from {tool}"

        manager = FakeManager()
        spec = mcp_tool_to_spec(
            server_name="test_server",
            tool_name="read_file",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            manager=manager,
        )

        assert isinstance(spec, ToolSpec)
        assert spec.name == "read_file"
        assert spec.description == "Read a file"
        assert spec.parameters["type"] == "object"
        assert spec.async_callable is not None

    @pytest.mark.asyncio
    async def test_callable_routes_through_manager(self):
        """Verify the ToolSpec async_callable routes calls through the manager."""

        calls = []

        class FakeManager:
            async def call_tool(self, server, tool, args):
                calls.append((server, tool, args))
                return "ok"

        manager = FakeManager()
        spec = mcp_tool_to_spec(
            server_name="fs",
            tool_name="read_file",
            description="Read a file",
            input_schema={},
            manager=manager,
        )

        result = await spec.execute(path="/tmp/test.txt")
        assert result == "ok"
        assert calls == [("fs", "read_file", {"path": "/tmp/test.txt"})]

    def test_empty_schema_defaults(self):
        """Empty input_schema gets sensible defaults."""

        class FakeManager:
            async def call_tool(self, server, tool, args):
                return None

        spec = mcp_tool_to_spec(
            server_name="s",
            tool_name="t",
            description="",
            input_schema={},
            manager=FakeManager(),
        )
        assert spec.parameters["type"] == "object"
        assert spec.parameters["properties"] == {}

    @pytest.mark.asyncio
    async def test_discover_mcp_tool_specs(self):
        """discover_mcp_tool_specs converts all raw tools from manager."""

        class FakeManager:
            async def discover_tools(self):
                return [
                    {"server_name": "s1", "tool_name": "t1", "description": "Tool 1", "input_schema": {}},
                    {"server_name": "s2", "tool_name": "t2", "description": "Tool 2", "input_schema": {"type": "object"}},
                ]

        specs = await discover_mcp_tool_specs(FakeManager())
        assert len(specs) == 2
        assert specs[0].name == "t1"
        assert specs[1].name == "t2"


# ---------------------------------------------------------------------------
# use_tools().with_mcp_servers()
# ---------------------------------------------------------------------------

class TestUseToolsWithMCPServers:
    def test_with_mcp_servers_fluent(self):
        """with_mcp_servers returns new solver with MCP specs added."""
        spec = MCPServerSpec(name="fs", transport="stdio", command="mcp-fs")
        solver = use_tools().with_mcp_servers(spec)
        assert solver._mcp_servers == (spec,)

    def test_with_mcp_servers_accumulates(self):
        """Multiple with_mcp_servers calls accumulate specs."""
        s1 = MCPServerSpec(name="fs", transport="stdio", command="mcp-fs")
        s2 = MCPServerSpec(name="web", transport="sse", url="http://x/mcp")
        solver = use_tools().with_mcp_servers(s1).with_mcp_servers(s2)
        assert len(solver._mcp_servers) == 2

    def test_constructor_mcp_servers(self):
        """use_tools() accepts mcp_servers in constructor."""
        spec = MCPServerSpec(name="fs", transport="stdio", command="mcp-fs")
        solver = use_tools(mcp_servers=[spec])
        assert solver._mcp_servers == (spec,)

    @pytest.mark.asyncio
    async def test_mcp_servers_stored_in_state(self):
        """Solver stores MCP specs in state.output["_solver_mcp_servers"]."""
        spec = MCPServerSpec(name="fs", transport="stdio", command="mcp-fs")
        solver = use_tools().with_mcp_servers(spec)
        state = AgentState(messages=[])
        result = await solver(state, lambda **kw: state)
        mcp = result.output.get("_solver_mcp_servers", [])
        assert len(mcp) == 1
        assert mcp[0].name == "fs"

    def test_with_middleware_preserves_mcp(self):
        """with_middleware() preserves existing MCP servers."""
        spec = MCPServerSpec(name="fs", transport="stdio", command="mcp-fs")
        solver = use_tools().with_mcp_servers(spec).with_middleware("fake")
        assert solver._mcp_servers == (spec,)


# ---------------------------------------------------------------------------
# Solver resolve with mcp_servers
# ---------------------------------------------------------------------------

class TestSolverResolveMCP:
    def test_resolve_use_tools_with_mcp(self):
        """resolve_solver_chain parses mcp_servers in use_tools step."""
        from snowl.solver.resolve import resolve_solver_chain

        config = {
            "steps": [
                {"use_tools": {"tools": [], "mcp_servers": [{"name": "fs", "transport": "stdio", "command": "mcp-fs"}]}},
            ],
        }
        chain = resolve_solver_chain(config)
        assert chain is not None
        # The chain should be a UseToolsSolver
        if hasattr(chain, "_mcp_servers"):
            assert len(chain._mcp_servers) == 1
            assert chain._mcp_servers[0].name == "fs"

    def test_resolve_mcp_server_factory(self):
        """mcp_server factory creates MCPServerSpec from config."""
        from snowl.solver.resolve import _init_default_factories, _SOLVER_FACTORIES

        _init_default_factories()
        factory = _SOLVER_FACTORIES.get("mcp_server")
        assert factory is not None
        spec = factory(name="test", transport="stdio", command="echo")
        assert spec.name == "test"
        assert spec.transport == "stdio"


# ---------------------------------------------------------------------------
# MCPServerManager (mock-based)
# ---------------------------------------------------------------------------

class TestMCPServerManager:
    @pytest.mark.asyncio
    async def test_empty_specs_noop(self):
        """Manager with no specs starts and stops cleanly."""
        from snowl.runtime.mcp_manager import MCPServerManager

        manager = MCPServerManager([])
        await manager.start_all()
        assert manager.active_server_names == []
        await manager.stop_all()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Manager works as async context manager."""
        from snowl.runtime.mcp_manager import MCPServerManager

        async with MCPServerManager([]) as mgr:
            assert mgr.active_server_names == []

    def test_specs_property(self):
        """specs property returns the original specs."""
        from snowl.runtime.mcp_manager import MCPServerManager

        spec = MCPServerSpec(name="x", transport="stdio", command="echo")
        manager = MCPServerManager([spec])
        assert manager.specs == (spec,)
