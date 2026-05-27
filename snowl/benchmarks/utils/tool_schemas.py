"""Tool schema normalization utilities for benchmark adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def normalize_tool_schemas(
    raw_tools: Any,
    *,
    default_description_prefix: str = "Tool",
) -> list[dict[str, Any]]:
    """Normalize heterogeneous raw tool data into OpenAI function-calling format.

    Accepts arbitrary raw tool data (list of dicts in various shapes) and returns
    a list of ``{"type": "function", "function": {"name", "description", "parameters"}}``
    dicts.

    Args:
        raw_tools: Raw tool data from a dataset row or similar source.
        default_description_prefix: Prefix for generated default descriptions
            (e.g. ``"Function"`` for BFCL, ``"Tool"`` for AgentDojo).
    """
    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, (str, bytes, bytearray)):
        return []
    out: list[dict[str, Any]] = []
    for item in raw_tools:
        if not isinstance(item, Mapping):
            continue
        fn = item.get("function") if isinstance(item.get("function"), Mapping) else item
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        parameters = fn.get("parameters")
        if not isinstance(parameters, Mapping):
            parameters = {"type": "object", "properties": {}, "additionalProperties": False}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(fn.get("description") or f"{default_description_prefix} {name}."),
                    "parameters": dict(parameters),
                },
            }
        )
    return out
