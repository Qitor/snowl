from __future__ import annotations

from snowl.core import tool


@tool(required_ops=["terminal.exec", "process.run"])
def terminal_exec(command: str, timeout_sec: float = 180.0) -> str:
    """Placeholder terminal exec tool contract for schema discovery in examples."""
    _ = timeout_sec
    return f"tool_schema_only: {command}"

