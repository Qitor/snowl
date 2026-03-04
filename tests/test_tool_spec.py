from __future__ import annotations

from snowl.core import ToolSpec, build_tool_spec, resolve_tool_spec, tool


@tool(required_ops=["FileOps"])
def read_file(path: str, encoding: str = "utf-8") -> str:
    """Read a text file from workspace.

    Args:
        path: Absolute or relative file path.
        encoding: Text encoding name.
    """

    return f"{path}:{encoding}"


def test_tool_decorator_attaches_toolspec() -> None:
    spec = getattr(read_file, "__snowl_tool_spec__")
    assert isinstance(spec, ToolSpec)
    assert spec.name == "read_file"
    assert spec.description == "Read a text file from workspace."
    assert spec.required_ops == ("FileOps",)
    assert "path" in spec.parameters["properties"]
    assert "encoding" in spec.parameters["properties"]
    assert spec.parameters["properties"]["path"]["type"] == "string"
    assert spec.parameters["required"] == ["path"]


def test_build_tool_spec_uses_signature_and_docstring() -> None:
    def calc(expression: str, precision: int = 2) -> str:
        """Evaluate an arithmetic expression.

        Args:
            expression: Arithmetic expression text.
            precision: Decimal places for formatting.
        """

        return expression

    spec = build_tool_spec(calc)
    assert spec.name == "calc"
    assert spec.parameters["properties"]["expression"]["description"] == "Arithmetic expression text."
    assert spec.parameters["properties"]["precision"]["type"] == "integer"
    assert spec.parameters["required"] == ["expression"]


def test_resolve_tool_spec_supports_function_mapping_and_toolspec() -> None:
    def ping(host: str) -> str:
        return host

    mapping_spec = resolve_tool_spec(
        {
            "name": "ping",
            "description": "Ping a host",
            "parameters": {
                "type": "object",
                "properties": {"host": {"type": "string"}},
                "required": ["host"],
                "additionalProperties": False,
            },
            "callable": ping,
        }
    )
    assert mapping_spec.name == "ping"

    fn_spec = resolve_tool_spec(ping)
    assert fn_spec.name == "ping"

    direct_spec = resolve_tool_spec(fn_spec)
    assert direct_spec is fn_spec
