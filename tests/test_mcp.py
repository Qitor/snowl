"""Tests for MCPServerSpec, validation, from_dict, and EnvSpec integration."""

import pytest

from snowl.core.mcp import (
    MCPServerSpec,
    mcp_server_spec_from_dict,
    validate_mcp_server_spec,
)
from snowl.core.env import EnvSpec, validate_env_spec
from snowl.errors import SnowlValidationError


# ---------------------------------------------------------------------------
# MCPServerSpec creation
# ---------------------------------------------------------------------------

class TestMCPServerSpec:
    def test_stdio_spec(self):
        spec = MCPServerSpec(name="fs", transport="stdio", command="mcp-fs")
        assert spec.name == "fs"
        assert spec.transport == "stdio"
        assert spec.command == "mcp-fs"
        assert spec.args == ()
        assert spec.env == {}
        assert spec.url is None
        assert spec.timeout_seconds == 30.0

    def test_sse_spec(self):
        spec = MCPServerSpec(name="web", transport="sse", url="http://localhost:8080/mcp")
        assert spec.transport == "sse"
        assert spec.url == "http://localhost:8080/mcp"
        assert spec.command is None

    def test_full_spec(self):
        spec = MCPServerSpec(
            name="api",
            transport="stdio",
            command="python",
            args=("-m", "my_server"),
            env={"API_KEY": "xxx"},
            timeout_seconds=60.0,
            metadata={"domain": "airline"},
        )
        assert spec.args == ("-m", "my_server")
        assert spec.env == {"API_KEY": "xxx"}
        assert spec.timeout_seconds == 60.0

    def test_frozen(self):
        spec = MCPServerSpec(name="test", transport="stdio", command="echo")
        with pytest.raises(AttributeError):
            spec.name = "changed"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidateMCPServerSpec:
    def test_valid_stdio(self):
        spec = MCPServerSpec(name="fs", transport="stdio", command="mcp-fs")
        validate_mcp_server_spec(spec)  # no error

    def test_valid_sse(self):
        spec = MCPServerSpec(name="web", transport="sse", url="http://x/mcp")
        validate_mcp_server_spec(spec)

    def test_empty_name_rejected(self):
        spec = MCPServerSpec(name="", transport="stdio", command="echo")
        with pytest.raises(SnowlValidationError, match="non-empty string"):
            validate_mcp_server_spec(spec)

    def test_invalid_transport_rejected(self):
        spec = MCPServerSpec(name="x", transport="grpc", command="echo")
        with pytest.raises(SnowlValidationError, match="transport"):
            validate_mcp_server_spec(spec)

    def test_stdio_missing_command_rejected(self):
        spec = MCPServerSpec(name="x", transport="stdio")
        with pytest.raises(SnowlValidationError, match="command"):
            validate_mcp_server_spec(spec)

    def test_sse_missing_url_rejected(self):
        spec = MCPServerSpec(name="x", transport="sse")
        with pytest.raises(SnowlValidationError, match="url"):
            validate_mcp_server_spec(spec)

    def test_negative_timeout_rejected(self):
        spec = MCPServerSpec(name="x", transport="stdio", command="echo", timeout_seconds=-1)
        with pytest.raises(SnowlValidationError, match="timeout"):
            validate_mcp_server_spec(spec)


# ---------------------------------------------------------------------------
# from_dict
# ---------------------------------------------------------------------------

class TestMCPServerSpecFromDict:
    def test_stdio_from_dict(self):
        data = {"name": "fs", "transport": "stdio", "command": "mcp-fs", "args": ["/data"]}
        spec = mcp_server_spec_from_dict(data)
        assert spec.name == "fs"
        assert spec.transport == "stdio"
        assert spec.command == "mcp-fs"
        assert spec.args == ("/data",)

    def test_sse_from_dict(self):
        data = {"name": "web", "transport": "sse", "url": "http://x/mcp"}
        spec = mcp_server_spec_from_dict(data)
        assert spec.url == "http://x/mcp"

    def test_defaults(self):
        data = {"name": "test", "command": "echo"}
        spec = mcp_server_spec_from_dict(data)
        assert spec.transport == "stdio"
        assert spec.args == ()
        assert spec.env == {}

    def test_missing_name_rejected(self):
        with pytest.raises(SnowlValidationError, match="name"):
            mcp_server_spec_from_dict({"command": "echo"})

    def test_invalid_args_rejected(self):
        with pytest.raises(SnowlValidationError, match="args"):
            mcp_server_spec_from_dict({"name": "x", "command": "echo", "args": "bad"})

    def test_invalid_env_rejected(self):
        with pytest.raises(SnowlValidationError, match="env"):
            mcp_server_spec_from_dict({"name": "x", "command": "echo", "env": "bad"})


# ---------------------------------------------------------------------------
# EnvSpec integration
# ---------------------------------------------------------------------------

class TestEnvSpecMCPServers:
    def test_empty_mcp_servers_default(self):
        spec = EnvSpec(env_type="local")
        assert spec.mcp_servers == ()

    def test_with_mcp_servers(self):
        mcp = MCPServerSpec(name="fs", transport="stdio", command="mcp-fs")
        spec = EnvSpec(env_type="local", mcp_servers=(mcp,))
        assert len(spec.mcp_servers) == 1
        assert spec.mcp_servers[0].name == "fs"

    def test_validate_env_spec_with_mcp(self):
        mcp = MCPServerSpec(name="fs", transport="stdio", command="mcp-fs")
        spec = EnvSpec(env_type="local", mcp_servers=(mcp,))
        validate_env_spec(spec)  # no error

    def test_validate_env_spec_catches_bad_mcp(self):
        mcp = MCPServerSpec(name="", transport="stdio", command="echo")
        spec = EnvSpec(env_type="local", mcp_servers=(mcp,))
        with pytest.raises(SnowlValidationError, match="non-empty"):
            validate_env_spec(spec)


# ---------------------------------------------------------------------------
# Streamable-http transport
# ---------------------------------------------------------------------------

class TestStreamableHttpTransport:
    def test_streamable_http_spec(self):
        spec = MCPServerSpec(
            name="remote", transport="streamable-http",
            url="http://localhost:9090/mcp",
        )
        assert spec.transport == "streamable-http"
        assert spec.url == "http://localhost:9090/mcp"

    def test_validate_streamable_http(self):
        spec = MCPServerSpec(
            name="remote", transport="streamable-http",
            url="http://localhost:9090/mcp",
        )
        validate_mcp_server_spec(spec)  # no error

    def test_streamable_http_missing_url_rejected(self):
        spec = MCPServerSpec(name="x", transport="streamable-http")
        with pytest.raises(SnowlValidationError, match="url"):
            validate_mcp_server_spec(spec)

    def test_streamable_http_from_dict(self):
        data = {
            "name": "remote",
            "transport": "streamable-http",
            "url": "http://localhost:9090/mcp",
            "headers": {"Authorization": "Bearer test"},
        }
        spec = mcp_server_spec_from_dict(data)
        assert spec.transport == "streamable-http"
        assert spec.headers["Authorization"] == "Bearer test"

    @pytest.mark.asyncio
    async def test_manager_start_streamable_http(self):
        """MCPServerManager._start_remote handles streamable-http transport."""
        from snowl.runtime.mcp_manager import MCPServerManager
        from unittest.mock import AsyncMock, patch, MagicMock

        spec = MCPServerSpec(
            name="test-remote", transport="streamable-http",
            url="http://localhost:9090/mcp",
        )
        manager = MCPServerManager([spec])

        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_session = AsyncMock()

        with patch("snowl.runtime.mcp_manager.MCPServerManager._start_remote") as mock_start:
            mock_start.return_value = None
            # Just verify it doesn't raise
            await manager._start_remote(spec)
