from __future__ import annotations

import pytest

from snowl.core import ToolRegistry, ToolSpec, get_default_tool_registry, tool
from snowl.errors import SnowlValidationError


def test_tool_decorator_auto_registers_default_registry() -> None:
    registry = get_default_tool_registry()
    registry.clear()

    @tool
    def ping(host: str) -> str:
        """Ping host.

        Args:
            host: host name
        """

        return host

    spec = registry.get("ping")
    assert spec is not None
    assert spec.name == "ping"


def test_tool_registry_rejects_duplicate_name_different_callable() -> None:
    reg = ToolRegistry()

    def a(x: str) -> str:
        return x

    def b(x: str) -> str:
        return x

    reg.register(
        ToolSpec(
            name="dup",
            description="A",
            parameters={"type": "object", "properties": {}},
            callable=a,
        )
    )

    with pytest.raises(SnowlValidationError, match="already registered"):
        reg.register(
            ToolSpec(
                name="dup",
                description="B",
                parameters={"type": "object", "properties": {}},
                callable=b,
            )
        )
