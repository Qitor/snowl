"""Core step model for multi-step task execution.

Framework role:
- Defines ``TaskStep`` for declaring sequential evaluation steps within a Task.
- Enables multi-step evaluation patterns (e.g., setup -> execute -> verify).

Runtime/usage wiring:
- Used by ``MultiStepExecutor`` and the engine when a Task has non-empty ``steps``.

Change guardrails:
- ``TaskStep`` is a frozen dataclass; new optional fields must have defaults.
- ``steps=()`` on Task means single-step (backward compatible).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from snowl.core.env import EnvSpec


@dataclass(frozen=True)
class TaskStep:
    """A single step within a multi-step task.

    Reference: ``references/harbor/src/harbor/models/task/config.py`` (StepConfig)
    """

    step_id: str
    instruction: str
    env_spec: EnvSpec | None = None
    scorer_ids: tuple[str, ...] = ()
    min_reward: float = 0.0
    timeout_sec: float | None = None
    artifacts: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
