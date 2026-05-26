"""Tests for MCP connection robustness: healthcheck, reconnection, ensure_connected."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from snowl.core.mcp import MCPServerSpec
from snowl.runtime.mcp_manager import (
    MCPServerManager,
    _MAX_RECONNECT_ATTEMPTS,
    _RECONNECT_BASE_DELAY_SEC,
    _RECONNECT_BACKOFF_FACTOR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stdio_spec(name: str = "test") -> MCPServerSpec:
    return MCPServerSpec(name=name, transport="stdio", command="echo")


def _make_manager_with_session(name: str = "test") -> MCPServerManager:
    """Create a manager with a mocked active session."""
    spec = _stdio_spec(name)
    manager = MCPServerManager([spec])
    manager._spec_map[name] = spec
    mock_session = AsyncMock()
    manager._sessions[name] = mock_session
    return manager


# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------

class TestHealthcheck:
    @pytest.mark.asyncio
    async def test_alive_when_list_tools_succeeds(self):
        manager = _make_manager_with_session("srv")
        manager._sessions["srv"].list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        result = await manager.healthcheck("srv")
        assert result["alive"] is True
        assert result["server_name"] == "srv"

    @pytest.mark.asyncio
    async def test_dead_when_list_tools_raises(self):
        manager = _make_manager_with_session("srv")
        manager._sessions["srv"].list_tools = AsyncMock(side_effect=ConnectionError("lost"))
        result = await manager.healthcheck("srv")
        assert result["alive"] is False
        assert "lost" in result["details"]

    @pytest.mark.asyncio
    async def test_dead_when_no_session(self):
        manager = MCPServerManager([])
        result = await manager.healthcheck("missing")
        assert result["alive"] is False
        assert result["details"] == "no active session"


# ---------------------------------------------------------------------------
# Reconnection
# ---------------------------------------------------------------------------

class TestReconnect:
    @pytest.mark.asyncio
    async def test_reconnect_succeeds_on_first_attempt(self):
        manager = _make_manager_with_session("srv")
        with patch.object(manager, "_start_stdio", new_callable=AsyncMock):
            result = await manager.reconnect("srv")
        assert result is True

    @pytest.mark.asyncio
    async def test_reconnect_retries_on_failure(self):
        manager = _make_manager_with_session("srv")
        call_count = 0

        async def _flaky_start(spec):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("not ready")
            # On 3rd call, simulate success by adding session
            mock_session = AsyncMock()
            manager._sessions[spec.name] = mock_session

        with patch.object(manager, "_start_stdio", side_effect=_flaky_start):
            with patch("snowl.runtime.mcp_manager.asyncio.sleep", new_callable=AsyncMock):
                result = await manager.reconnect("srv")
        assert result is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_reconnect_fails_after_max_attempts(self):
        manager = _make_manager_with_session("srv")

        async def _always_fail(spec):
            raise ConnectionError("unreachable")

        with patch.object(manager, "_start_stdio", side_effect=_always_fail):
            with patch("snowl.runtime.mcp_manager.asyncio.sleep", new_callable=AsyncMock):
                result = await manager.reconnect("srv")
        assert result is False

    @pytest.mark.asyncio
    async def test_reconnect_returns_false_for_unknown_server(self):
        manager = MCPServerManager([])
        result = await manager.reconnect("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_reconnect_closes_stale_session(self):
        manager = _make_manager_with_session("srv")
        stale = manager._sessions["srv"]
        stale.close = AsyncMock()

        with patch.object(manager, "_start_stdio", new_callable=AsyncMock):
            await manager.reconnect("srv")

        stale.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reconnect_uses_exponential_backoff(self):
        manager = _make_manager_with_session("srv")
        sleep_delays = []

        async def _fake_sleep(delay):
            sleep_delays.append(delay)

        async def _always_fail(spec):
            raise ConnectionError("unreachable")

        with patch.object(manager, "_start_stdio", side_effect=_always_fail):
            with patch("snowl.runtime.mcp_manager.asyncio.sleep", side_effect=_fake_sleep):
                await manager.reconnect("srv")

        # Should sleep between attempts (not after the last one)
        expected = []
        delay = _RECONNECT_BASE_DELAY_SEC
        for i in range(_MAX_RECONNECT_ATTEMPTS - 1):
            expected.append(delay)
            delay *= _RECONNECT_BACKOFF_FACTOR
        assert sleep_delays == expected


# ---------------------------------------------------------------------------
# ensure_connected
# ---------------------------------------------------------------------------

class TestEnsureConnected:
    @pytest.mark.asyncio
    async def test_returns_true_when_healthy(self):
        manager = _make_manager_with_session("srv")
        manager._sessions["srv"].list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        result = await manager.ensure_connected("srv")
        assert result is True

    @pytest.mark.asyncio
    async def test_triggers_reconnect_when_unhealthy(self):
        manager = _make_manager_with_session("srv")
        # healthcheck will fail
        manager._sessions["srv"].list_tools = AsyncMock(side_effect=ConnectionError("down"))

        with patch.object(manager, "reconnect", new_callable=AsyncMock, return_value=True) as mock_recon:
            result = await manager.ensure_connected("srv")

        assert result is True
        mock_recon.assert_awaited_once_with("srv")

    @pytest.mark.asyncio
    async def test_returns_false_when_reconnect_fails(self):
        manager = _make_manager_with_session("srv")
        manager._sessions["srv"].list_tools = AsyncMock(side_effect=ConnectionError("down"))

        with patch.object(manager, "reconnect", new_callable=AsyncMock, return_value=False):
            result = await manager.ensure_connected("srv")
        assert result is False


# ---------------------------------------------------------------------------
# _store_stdio_process
# ---------------------------------------------------------------------------

class TestStoreStdioProcess:
    def test_extracts_process_from_stream(self):
        manager = MCPServerManager([])
        mock_proc = MagicMock(spec=asyncio.subprocess.Process)
        read_stream = MagicMock()
        read_stream._process = mock_proc
        write_stream = MagicMock()

        manager._store_stdio_process("srv", read_stream, write_stream)
        assert "srv" in manager._processes
        assert manager._processes["srv"] is mock_proc

    def test_tries_alternate_attribute_names(self):
        manager = MCPServerManager([])
        mock_proc = MagicMock(spec=asyncio.subprocess.Process)
        read_stream = MagicMock()
        read_stream._process = None
        read_stream.process = None
        read_stream._transport = mock_proc
        write_stream = MagicMock()

        manager._store_stdio_process("srv", read_stream, write_stream)
        assert manager._processes["srv"] is mock_proc

    def test_no_process_found_is_ok(self):
        """If no process can be extracted, no error is raised."""
        manager = MCPServerManager([])
        read_stream = MagicMock(spec=[])  # no _process attr
        write_stream = MagicMock(spec=[])
        manager._store_stdio_process("srv", read_stream, write_stream)
        assert "srv" not in manager._processes
