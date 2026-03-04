"""Concrete local environment implementation (MVP)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from snowl.core.env import EnvSpec, validate_env_spec


@dataclass
class LocalEnv:
    """Simple concrete environment carrying ops and config metadata."""

    env_spec: EnvSpec
    state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_env_spec(self.env_spec)

    @property
    def env_id(self) -> str:
        return f"{self.env_spec.env_type}:local"

    @property
    def provided_ops(self) -> tuple[str, ...]:
        return self.env_spec.provided_ops

    def reset(self) -> dict[str, Any]:
        self.state = {}
        return {"status": "reset"}

    def close(self) -> None:
        self.state.clear()
