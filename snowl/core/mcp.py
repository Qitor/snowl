"""Core MCP (Model Context Protocol) server specification.

Framework role:
- Defines `MCPServerSpec`, a pure data model for declaring MCP servers in evaluations.
- No third-party imports — the `mcp` SDK is only used at the runtime layer.

Runtime/usage wiring:
- Consumed by `EnvSpec.mcp_servers`, `UseToolsSolver.with_mcp_servers()`,
  `MCPServerManager`, and `project_config.py` parsing.

Change guardrails:
- This module must stay framework-independent (zero third-party imports).
- Adding new transport types requires updating `validate_mcp_server_spec`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from snowl.errors import SnowlValidationError

_VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")


@dataclass(frozen=True)
class MCPServerSpec:
    """Declarative spec for an MCP server connection.

    Pure data model — no SDK imports. The runtime ``MCPServerManager``
    interprets these specs to start/discover/stop servers.

    Attributes:
        name: Unique server identifier within an evaluation.
        transport: Connection mode — ``"stdio"``, ``"sse"``, or ``"streamable-http"``.
        command: Executable for stdio transport (e.g. ``"python"``).
        args: Positional arguments for the stdio command.
        env: Environment variables passed to the subprocess.
        url: URL for sse / streamable-http transports.
        headers: HTTP headers for remote transports.
        timeout_seconds: Startup timeout per server.
        metadata: Arbitrary metadata for benchmark/tool hints.
    """

    name: str
    transport: str = "stdio"
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)


def validate_mcp_server_spec(spec: MCPServerSpec) -> None:
    """Validate an MCPServerSpec, raising SnowlValidationError on problems."""
    if not isinstance(spec.name, str) or not spec.name.strip():
        raise SnowlValidationError("MCPServerSpec.name must be a non-empty string.")

    if spec.transport not in _VALID_TRANSPORTS:
        raise SnowlValidationError(
            f"MCPServerSpec.transport must be one of {_VALID_TRANSPORTS}, "
            f"got '{spec.transport}'."
        )

    if spec.transport == "stdio":
        if not spec.command or not spec.command.strip():
            raise SnowlValidationError(
                "MCPServerSpec.command is required for stdio transport."
            )
    else:
        if not spec.url or not spec.url.strip():
            raise SnowlValidationError(
                f"MCPServerSpec.url is required for {spec.transport} transport."
            )

    if spec.timeout_seconds <= 0:
        raise SnowlValidationError("MCPServerSpec.timeout_seconds must be > 0.")


def mcp_server_spec_from_dict(data: dict[str, Any]) -> MCPServerSpec:
    """Construct an MCPServerSpec from a project.yml dict.

    Args:
        data: Dict with keys like ``name``, ``transport``, ``command``, etc.

    Returns:
        A validated MCPServerSpec instance.
    """
    if not isinstance(data, dict):
        raise SnowlValidationError("MCP server config must be a mapping.")

    name = data.get("name")
    if not name or not str(name).strip():
        raise SnowlValidationError("MCP server config must include a non-empty 'name'.")

    args_raw = data.get("args", [])
    if not isinstance(args_raw, (list, tuple)):
        raise SnowlValidationError("MCP server 'args' must be a list.")

    env_raw = data.get("env", {})
    if not isinstance(env_raw, dict):
        raise SnowlValidationError("MCP server 'env' must be a mapping.")

    headers_raw = data.get("headers", {})
    if not isinstance(headers_raw, dict):
        raise SnowlValidationError("MCP server 'headers' must be a mapping.")

    spec = MCPServerSpec(
        name=str(name).strip(),
        transport=str(data.get("transport", "stdio")).strip(),
        command=data.get("command"),
        args=tuple(str(a) for a in args_raw),
        env={str(k): str(v) for k, v in env_raw.items()},
        url=data.get("url"),
        headers={str(k): str(v) for k, v in headers_raw.items()},
        timeout_seconds=float(data.get("timeout_seconds", 30.0)),
        metadata=dict(data.get("metadata", {})),
    )
    validate_mcp_server_spec(spec)
    return spec
