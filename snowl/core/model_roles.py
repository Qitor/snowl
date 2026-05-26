"""Model roles: assign different models to distinct roles within an evaluation.

Framework role:
- Defines the ModelRole enum and ModelAssignment dataclass for mapping
  models to functional roles (agent, judge, attacker, target) within an eval.
- Enables multi-model evaluations where different participants use different providers.

Runtime/usage wiring:
- Model assignments are configured via project config and consumed by the
  runtime engine when resolving model clients for different eval participants.

Change guardrails:
- ModelRole values are part of the project config schema; changes require
  migration support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from snowl.errors import SnowlValidationError


class ModelRole(str, Enum):
    """Functional role a model plays in an evaluation."""
    AGENT = "agent"          # The agent being evaluated
    JUDGE = "judge"          # LLM-as-judge scorer
    ATTACKER = "attacker"    # Red-team attacker
    TARGET = "target"        # Attack target model


@dataclass(frozen=True)
class ModelAssignment:
    """Mapping of a model to a functional role."""
    role: ModelRole
    model: str
    provider_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.role, ModelRole):
            raise SnowlValidationError(
                f"ModelAssignment.role must be a ModelRole, got {type(self.role).__name__}"
            )
        if not isinstance(self.model, str) or not self.model.strip():
            raise SnowlValidationError(
                "ModelAssignment.model must be a non-empty string."
            )


class ModelRoleRegistry:
    """Registry of model assignments for an evaluation.

    Usage::

        registry = ModelRoleRegistry()
        registry.assign(ModelAssignment(role=ModelRole.AGENT, model="gpt-4o"))
        registry.assign(ModelAssignment(role=ModelRole.JUDGE, model="claude-3.5"))

        agent_model = registry.resolve(ModelRole.AGENT)
    """

    def __init__(self) -> None:
        self._assignments: dict[ModelRole, ModelAssignment] = {}

    def assign(self, assignment: ModelAssignment) -> None:
        """Register a model for a role. Overwrites any previous assignment."""
        self._assignments[assignment.role] = assignment

    def resolve(self, role: ModelRole, default: str | None = None) -> str | None:
        """Get the model name for a role, or default if not assigned."""
        assignment = self._assignments.get(role)
        if assignment is not None:
            return assignment.model
        return default

    def get_assignment(self, role: ModelRole) -> ModelAssignment | None:
        """Get the full assignment for a role."""
        return self._assignments.get(role)

    def assigned_roles(self) -> list[ModelRole]:
        """Return roles that have assignments."""
        return list(self._assignments.keys())

    def all_assignments(self) -> list[ModelAssignment]:
        """Return all assignments."""
        return list(self._assignments.values())

    def clear(self) -> None:
        self._assignments.clear()


def model_assignments_from_config(config: Mapping[str, Any]) -> ModelRoleRegistry:
    """Build a ModelRoleRegistry from a project config dict.

    Expected config format::

        models:
          agent:
            model: gpt-4o
            provider_id: openai
          judge:
            model: claude-3.5
    """
    registry = ModelRoleRegistry()
    models_config = config.get("models")
    if not models_config or not isinstance(models_config, Mapping):
        return registry

    for role_name, role_config in models_config.items():
        if not isinstance(role_config, Mapping):
            continue
        try:
            role = ModelRole(role_name)
        except ValueError:
            continue  # Skip unknown roles

        model = role_config.get("model")
        if not model:
            continue

        registry.assign(ModelAssignment(
            role=role,
            model=str(model),
            provider_id=role_config.get("provider_id"),
            params=dict(role_config.get("params") or {}),
        ))

    return registry
