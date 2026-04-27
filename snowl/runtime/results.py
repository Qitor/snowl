"""Trial outcome serialization and failure classification helpers."""

from __future__ import annotations

from typing import Any

from snowl.core import Score, TaskResult
from snowl.runtime import TrialOutcome


def to_serializable_outcome(outcome: TrialOutcome, *, schema_version: str, schema_uri: str) -> dict[str, Any]:
    scores = {
        k: {
            "value": v.value,
            "explanation": v.explanation,
            "metadata": dict(v.metadata),
        }
        for k, v in outcome.scores.items()
    }
    return {
        "schema_version": schema_version,
        "schema_uri": schema_uri,
        "task_result": outcome.task_result.to_dict(),
        "scores": scores,
        "trace": outcome.trace,
    }


def trial_key_from_task_result_dict(task_result: dict[str, Any]) -> str | None:
    payload = dict(task_result.get("payload") or {})
    task_id = str(task_result.get("task_id") or "").strip()
    agent_id = str(task_result.get("agent_id") or "").strip()
    variant_id = str(payload.get("variant_id") or "default").strip() or "default"
    sample_id = task_result.get("sample_id")
    if not task_id or not agent_id or sample_id is None:
        return None
    return f"{task_id}::{agent_id}::{variant_id}::{sample_id}"


def outcome_from_serialized(row: dict[str, Any]) -> TrialOutcome:
    task_result = TaskResult.from_dict(dict(row.get("task_result") or {}))
    scores = {
        str(k): Score(
            value=float(v.get("value") or 0.0),
            explanation=v.get("explanation"),
            metadata=dict(v.get("metadata") or {}),
        )
        for k, v in dict(row.get("scores") or {}).items()
        if isinstance(v, dict)
    }
    return TrialOutcome(task_result=task_result, scores=scores, trace=dict(row.get("trace") or {}))


def classify_failure_from_serialized(row: dict[str, Any]) -> str:
    task_result = dict(row.get("task_result") or {})
    status = str(task_result.get("status") or "").strip().lower()
    error = dict(task_result.get("error") or {})
    code = str(error.get("code") or "").strip().lower()
    message = str(error.get("message") or "").strip().lower()

    if status == "cancelled":
        return "user.cancelled"
    if status == "incorrect":
        return "semantic.failure"
    if code.startswith("container_") or "docker" in code or "compose" in code or "docker" in message:
        return "infra.container"
    if code.startswith("scorer_") or "judge" in code or "judge" in message:
        return "evaluation.judge"
    if code.startswith("provider_") or "quota" in message or "rate limit" in message or "api" in message:
        return "infra.provider"
    if code.startswith("scheduler_"):
        return "infra.scheduler"
    if status in {"error", "limit_exceeded"}:
        return "task.execution"
    return "unknown"
