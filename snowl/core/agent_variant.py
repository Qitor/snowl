"""Core variant contract for binding one logical agent to multiple model/config variants.

Framework role:
- Defines `AgentVariant` metadata container and adapter wrapper that preserves the `Agent` runtime interface.
- Enforces variant identity validity (`agent_id`, `variant_id`, params/provenance mapping).

Runtime/usage wiring:
- Used by eval planning to expand one agent declaration into multiple runnable trial identities.

Change guardrails:
- Keep variant identity semantics stable; compare tables and rerun routing depend on these keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from snowl.core.agent import validate_agent
from snowl.errors import SnowlValidationError


@dataclass(frozen=True)
class AgentVariant:
    agent: Any
    agent_id: str
    variant_id: str
    model: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentVariantAdapter:
    """Agent wrapper carrying variant metadata while preserving Agent contract."""

    agent: Any
    agent_id: str
    variant_id: str
    model: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    async def run(self, state, context, tools=None):
        return await self.agent.run(state, context, tools=tools)


def validate_agent_variant(variant: AgentVariant) -> None:
    validate_agent(variant.agent)
    if not isinstance(variant.agent_id, str) or not variant.agent_id.strip():
        raise SnowlValidationError("AgentVariant.agent_id must be a non-empty string.")
    if not isinstance(variant.variant_id, str) or not variant.variant_id.strip():
        raise SnowlValidationError("AgentVariant.variant_id must be a non-empty string.")
    if variant.model is not None and not isinstance(variant.model, str):
        raise SnowlValidationError("AgentVariant.model must be a string or None.")
    if not isinstance(variant.params, Mapping):
        raise SnowlValidationError("AgentVariant.params must be a mapping.")
    if not isinstance(variant.provenance, Mapping):
        raise SnowlValidationError("AgentVariant.provenance must be a mapping.")


def make_agent_variant(
    *,
    agent: Any,
    agent_id: str,
    variant_id: str,
    model: str | None = None,
    params: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> AgentVariant:
    variant = AgentVariant(
        agent=agent,
        agent_id=agent_id,
        variant_id=variant_id,
        model=model,
        params=dict(params or {}),
        provenance=dict(provenance or {}),
    )
    validate_agent_variant(variant)
    return variant


def bind_agent_variant(variant: AgentVariant) -> AgentVariantAdapter:
    validate_agent_variant(variant)
    return AgentVariantAdapter(
        agent=variant.agent,
        agent_id=variant.agent_id,
        variant_id=variant.variant_id,
        model=variant.model,
        params=dict(variant.params),
        provenance=dict(variant.provenance),
    )

