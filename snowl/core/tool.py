"""Tool contracts and decorator-based ToolSpec generation."""

from __future__ import annotations

import inspect
import re
import types
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Union, get_args, get_origin, get_type_hints, runtime_checkable

from snowl.errors import SnowlValidationError


ToolCallable = Callable[..., Any]


@runtime_checkable
class ToolLike(Protocol):
    __snowl_tool_spec__: "ToolSpec"


@dataclass(frozen=True)
class ToolSpec:
    """Normalized tool contract used by agents/runtime."""

    name: str
    description: str
    parameters: dict[str, Any]
    callable: ToolCallable
    required_ops: tuple[str, ...] = field(default_factory=tuple)

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry for ToolSpec lookup and discovery."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool_spec: ToolSpec, *, allow_override: bool = False) -> None:
        existing = self._tools.get(tool_spec.name)
        if existing is not None and not allow_override:
            if existing.callable is tool_spec.callable:
                return
            raise SnowlValidationError(
                f"Tool '{tool_spec.name}' already registered with a different callable."
            )
        self._tools[tool_spec.name] = tool_spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def clear(self) -> None:
        self._tools.clear()


_DEFAULT_TOOL_REGISTRY = ToolRegistry()


def get_default_tool_registry() -> ToolRegistry:
    return _DEFAULT_TOOL_REGISTRY


def _parse_docstring(fn: ToolCallable) -> tuple[str, dict[str, str]]:
    doc = inspect.getdoc(fn) or ""
    if not doc.strip():
        return "", {}

    lines = doc.splitlines()
    description = lines[0].strip()

    param_docs: dict[str, str] = {}
    in_args = False
    for raw_line in lines[1:]:
        line = raw_line.rstrip()

        if not in_args and line.strip() in {"Args:", "Arguments:"}:
            in_args = True
            continue

        if not in_args:
            continue

        if not line.strip():
            continue

        # New section header ends args block.
        if re.match(r"^[A-Za-z][A-Za-z0-9_ ]+:$", line.strip()):
            break

        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$", line)
        if m:
            param_docs[m.group(1)] = m.group(2).strip()

    return description, param_docs


def _json_schema_for_annotation(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Signature.empty:
        return {"type": "string"}

    origin = get_origin(annotation)
    args = get_args(annotation)

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation in {dict, Mapping}:
        return {"type": "object"}
    if annotation in {list, tuple, set}:
        return {"type": "array"}

    if origin in {list, tuple, set}:
        item_schema = {"type": "string"}
        if args:
            item_schema = _json_schema_for_annotation(args[0])
        return {"type": "array", "items": item_schema}

    if origin in {dict, Mapping}:
        return {"type": "object"}

    if origin is None and annotation is Any:
        return {"type": "string"}

    if origin in {Union, types.UnionType}:
        non_none = [t for t in args if t is not type(None)]  # noqa: E721
        if not non_none:
            return {"type": "string"}
        schema = _json_schema_for_annotation(non_none[0])
        schema["nullable"] = True
        return schema

    return {"type": "string"}


def build_tool_spec(
    fn: ToolCallable,
    *,
    name: str | None = None,
    description: str | None = None,
    required_ops: list[str] | tuple[str, ...] | None = None,
) -> ToolSpec:
    if not callable(fn):
        raise SnowlValidationError("Tool must be callable.")

    sig = inspect.signature(fn)
    type_hints = get_type_hints(fn)
    doc_summary, param_docs = _parse_docstring(fn)

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            raise SnowlValidationError(
                f"Tool '{fn.__name__}' cannot use *args/**kwargs in MVP contract."
            )

        annotation = type_hints.get(param_name, param.annotation)
        schema = _json_schema_for_annotation(annotation)
        if param_name in param_docs:
            schema["description"] = param_docs[param_name]

        properties[param_name] = schema

        if param.default is inspect.Signature.empty:
            required.append(param_name)

    resolved_name = (name or fn.__name__).strip()
    if not resolved_name:
        raise SnowlValidationError("Tool name must be non-empty.")

    resolved_description = (description or doc_summary or f"Tool function '{resolved_name}'.").strip()

    parameters = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }

    return ToolSpec(
        name=resolved_name,
        description=resolved_description,
        parameters=parameters,
        callable=fn,
        required_ops=tuple(required_ops or ()),
    )


def tool(
    fn: ToolCallable | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    required_ops: list[str] | tuple[str, ...] | None = None,
    registry: ToolRegistry | None = None,
):
    """Decorator to build and attach ToolSpec from function signature/docstring."""

    def decorator(inner_fn: ToolCallable) -> ToolCallable:
        spec = build_tool_spec(
            inner_fn,
            name=name,
            description=description,
            required_ops=required_ops,
        )
        setattr(inner_fn, "__snowl_tool_spec__", spec)
        (registry or get_default_tool_registry()).register(spec)
        return inner_fn

    if fn is not None:
        return decorator(fn)

    return decorator


def resolve_tool_spec(tool_obj: Any) -> ToolSpec:
    if isinstance(tool_obj, ToolSpec):
        return tool_obj

    spec = getattr(tool_obj, "__snowl_tool_spec__", None)
    if isinstance(spec, ToolSpec):
        return spec

    if isinstance(tool_obj, Mapping):
        name = str(tool_obj.get("name", "")).strip()
        callable_fn = tool_obj.get("callable")
        if not name or not callable(callable_fn):
            raise SnowlValidationError(
                "Mapping tool must include non-empty 'name' and callable 'callable'."
            )
        return ToolSpec(
            name=name,
            description=str(tool_obj.get("description", "")).strip() or f"Tool '{name}'.",
            parameters=dict(
                tool_obj.get(
                    "parameters",
                    {"type": "object", "properties": {}, "additionalProperties": False},
                )
            ),
            callable=callable_fn,
            required_ops=tuple(tool_obj.get("required_ops", ()) or ()),
        )

    if callable(tool_obj):
        return build_tool_spec(tool_obj)

    raise SnowlValidationError("Unable to resolve ToolSpec from tool object.")
