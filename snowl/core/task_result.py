"""Canonical trial outcome schema shared by runtime, scorers, artifacts, and observability.

Framework role:
- Defines stable status/timing/usage/error/artifact payload shapes for one executed trial.
- Provides serialization helpers used by artifact persistence and replay/recovery tooling.

Runtime/usage wiring:
- Produced by runtime engine, consumed by scorers, aggregators, UI monitor, and web APIs.

Change guardrails:
- Consider this a high-stability contract; field/name changes require coordinated reader updates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from snowl.errors import SnowlValidationError


class TaskStatus(str, Enum):
    SUCCESS = "success"
    INCORRECT = "incorrect"
    LIMIT_EXCEEDED = "limit_exceeded"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Timing:
    started_at_ms: int
    ended_at_ms: int
    duration_ms: int


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactRef:
    name: str
    uri: str
    media_type: str | None = None


@dataclass(frozen=True)
class TaskResult:
    # stable identity
    task_id: str
    agent_id: str
    sample_id: str | None
    seed: int | None

    # stable runtime outcome
    status: TaskStatus
    final_output: dict[str, Any] = field(default_factory=dict)
    timing: Timing | None = None
    usage: Usage | None = None
    error: ErrorInfo | None = None
    artifacts: list[ArtifactRef] = field(default_factory=list)

    # extensibility bucket
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskResult":
        status = TaskStatus(data["status"])

        timing_data = data.get("timing")
        timing = Timing(**timing_data) if timing_data else None

        usage_data = data.get("usage")
        usage = Usage(**usage_data) if usage_data else None

        error_data = data.get("error")
        error = ErrorInfo(**error_data) if error_data else None

        artifacts_data = data.get("artifacts", [])
        artifacts = [ArtifactRef(**item) for item in artifacts_data]

        return cls(
            task_id=data["task_id"],
            agent_id=data["agent_id"],
            sample_id=data.get("sample_id"),
            seed=data.get("seed"),
            status=status,
            final_output=data.get("final_output", {}),
            timing=timing,
            usage=usage,
            error=error,
            artifacts=artifacts,
            payload=data.get("payload", {}),
        )


def validate_task_result(result: TaskResult) -> None:
    if not result.task_id:
        raise SnowlValidationError("TaskResult.task_id must be non-empty.")

    if not result.agent_id:
        raise SnowlValidationError("TaskResult.agent_id must be non-empty.")

    if not isinstance(result.status, TaskStatus):
        raise SnowlValidationError("TaskResult.status must be a TaskStatus enum value.")

    if result.status == TaskStatus.ERROR and result.error is None:
        raise SnowlValidationError(
            "TaskResult.error must be provided when status is 'error'."
        )
