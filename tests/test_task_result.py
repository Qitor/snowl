from __future__ import annotations

import pytest

from snowl.core import (
    ArtifactRef,
    ErrorInfo,
    TaskResult,
    TaskStatus,
    Timing,
    Usage,
    validate_task_result,
)
from snowl.errors import SnowlValidationError


def test_task_result_roundtrip_serialization() -> None:
    result = TaskResult(
        task_id="task-1",
        agent_id="chat-agent",
        sample_id="sample-1",
        seed=42,
        status=TaskStatus.SUCCESS,
        final_output={"answer": "42"},
        timing=Timing(started_at_ms=10, ended_at_ms=20, duration_ms=10),
        usage=Usage(input_tokens=5, output_tokens=3, total_tokens=8, estimated_cost_usd=0.001),
        artifacts=[ArtifactRef(name="trace", uri="file:///tmp/trace.json")],
        payload={"custom": {"foo": "bar"}},
    )

    payload = result.to_dict()
    restored = TaskResult.from_dict(payload)
    assert restored == result


def test_validate_task_result_rejects_empty_identity() -> None:
    result = TaskResult(
        task_id="",
        agent_id="chat-agent",
        sample_id="sample-1",
        seed=1,
        status=TaskStatus.SUCCESS,
    )
    with pytest.raises(SnowlValidationError, match="task_id"):
        validate_task_result(result)


def test_validate_task_result_error_requires_error_info() -> None:
    result = TaskResult(
        task_id="task-1",
        agent_id="chat-agent",
        sample_id="sample-1",
        seed=1,
        status=TaskStatus.ERROR,
        error=None,
    )
    with pytest.raises(SnowlValidationError, match="must be provided"):
        validate_task_result(result)


def test_validate_task_result_error_with_error_info_is_ok() -> None:
    result = TaskResult(
        task_id="task-1",
        agent_id="chat-agent",
        sample_id="sample-1",
        seed=1,
        status=TaskStatus.ERROR,
        error=ErrorInfo(code="runtime_error", message="boom"),
    )
    validate_task_result(result)
