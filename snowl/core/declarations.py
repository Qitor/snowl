"""Autodiscovery declaration metadata for task/agent/scorer objects.

Framework role:
- Provides `declare(...)` metadata stamping and fallback registry for objects that cannot hold attributes.
- Tracks declaration order so eval autodiscovery can preserve deterministic load ordering.

Runtime/usage wiring:
- Used by `@task`, `@agent`, and `@scorer` decorators in core contracts.

Change guardrails:
- Maintain backward-compatible metadata keys; discovery behavior depends on these attribute names.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from typing import Any, Literal


DeclarationKind = Literal["task", "agent", "scorer"]

_DECL_KIND_ATTR = "__snowl_declaration_kind__"
_DECL_ID_ATTR = "__snowl_declaration_id__"
_DECL_METADATA_ATTR = "__snowl_declaration_metadata__"
_DECL_ORDER_ATTR = "__snowl_declaration_order__"

_fallback_registry: dict[int, "Declaration"] = {}
_order_counter = count(1)


@dataclass(frozen=True)
class Declaration:
    kind: DeclarationKind
    object_id: str | None
    metadata: dict[str, Any]
    order: int


def declare(
    value: Any,
    *,
    kind: DeclarationKind,
    object_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    order = next(_order_counter)
    decl = Declaration(
        kind=kind,
        object_id=object_id.strip() if isinstance(object_id, str) and object_id.strip() else None,
        metadata=dict(metadata or {}),
        order=order,
    )
    try:
        setattr(value, _DECL_KIND_ATTR, decl.kind)
        setattr(value, _DECL_ID_ATTR, decl.object_id)
        setattr(value, _DECL_METADATA_ATTR, dict(decl.metadata))
        setattr(value, _DECL_ORDER_ATTR, decl.order)
    except Exception:
        _fallback_registry[id(value)] = decl
    return value


def get_declaration(value: Any) -> Declaration | None:
    kind = getattr(value, _DECL_KIND_ATTR, None)
    if isinstance(kind, str):
        return Declaration(
            kind=kind,  # type: ignore[arg-type]
            object_id=getattr(value, _DECL_ID_ATTR, None),
            metadata=dict(getattr(value, _DECL_METADATA_ATTR, {}) or {}),
            order=int(getattr(value, _DECL_ORDER_ATTR, 0) or 0),
        )
    return _fallback_registry.get(id(value))


def has_declaration(value: Any, *, kind: DeclarationKind | None = None) -> bool:
    decl = get_declaration(value)
    if decl is None:
        return False
    if kind is not None and decl.kind != kind:
        return False
    return True

