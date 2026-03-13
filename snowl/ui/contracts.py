"""UI-facing event/state contracts and reducer logic for runtime monitoring.

Framework role:
- Normalizes raw runtime events into typed `UIEvent`s and phase labels.
- Maintains task-level monitor state machine (`queued -> running -> scoring -> terminal states`).

Runtime/usage wiring:
- Shared by CLI live renderer and web monitor code paths to keep status semantics aligned.

Change guardrails:
- Event-name to phase/status mapping is contract-critical for observability; update docs/tests when altered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from snowl.core.scorer import Score, ScoreMap


class EventPhase(str, Enum):
    PLAN = "plan"
    ENV = "env"
    TASK = "task"
    AGENT = "agent"
    SCORER = "scorer"
    ERROR = "error"
    CONTROL = "control"
    SUMMARY = "summary"


@dataclass(frozen=True)
class UIEvent:
    run_id: str
    ts_ms: int
    phase: EventPhase
    event: str
    task_id: str | None
    agent_id: str | None
    variant_id: str | None
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ts_ms": self.ts_ms,
            "phase": self.phase.value,
            "event": self.event,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "variant_id": self.variant_id,
            "message": self.message,
            "payload": dict(self.payload),
        }


def infer_phase(event_name: str) -> EventPhase:
    name = (event_name or "").lower()
    if name.startswith("runtime.plan"):
        return EventPhase.PLAN
    if ".sandbox." in name or ".container." in name or ".compose." in name or name.startswith("env."):
        return EventPhase.ENV
    if name.startswith("runtime.task"):
        return EventPhase.TASK
    if name.startswith("runtime.scorer") or ".judge." in name or ".score" in name:
        return EventPhase.SCORER
    if name.startswith("runtime.trial") or ".agent" in name:
        return EventPhase.AGENT
    if "error" in name or "fail" in name:
        return EventPhase.ERROR
    if name.startswith("ui.control"):
        return EventPhase.CONTROL
    if name.startswith("runtime.summary"):
        return EventPhase.SUMMARY
    return EventPhase.AGENT


def normalize_ui_event(
    event: Mapping[str, Any],
    *,
    run_id: str,
    ts_ms: int,
    default_task_id: str | None = None,
    default_agent_id: str | None = None,
    default_variant_id: str | None = None,
) -> UIEvent:
    event_name = str(event.get("event", "runtime.event"))
    phase = infer_phase(event_name)
    message = str(
        event.get("message")
        or event.get("code")
        or event.get("status")
        or ""
    ).strip()
    return UIEvent(
        run_id=run_id,
        ts_ms=ts_ms,
        phase=phase,
        event=event_name,
        task_id=(str(event.get("task_id")) if event.get("task_id") is not None else default_task_id),
        agent_id=(str(event.get("agent_id")) if event.get("agent_id") is not None else default_agent_id),
        variant_id=(
            str(event.get("variant_id"))
            if event.get("variant_id") is not None
            else (default_variant_id or "default")
        ),
        message=message,
        payload={
            k: v
            for k, v in event.items()
            if k not in {"event", "task_id", "agent_id", "variant_id", "message"}
        },
    )


class TaskExecutionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SCORING = "scoring"
    SUCCESS = "success"
    INCORRECT = "incorrect"
    ERROR = "error"
    CANCELLED = "cancelled"
    LIMIT_EXCEEDED = "limit_exceeded"


@dataclass
class TaskMonitorState:
    task_id: str
    agent_id: str
    variant_id: str
    sample_id: str | None
    status: TaskExecutionStatus = TaskExecutionStatus.QUEUED
    step_count: int = 0
    started_at_ms: int | None = None
    ended_at_ms: int | None = None
    duration_ms: int | None = None
    latest_action: str | None = None
    latest_observation: str | None = None
    latest_message: str | None = None
    scorer_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def key(self) -> str:
        sample_token = self.sample_id or "-"
        return f"{self.task_id}::{self.agent_id}::{self.variant_id}::{sample_token}"


class TaskMonitor:
    """Event-driven task monitor with deterministic state transitions."""

    def __init__(self) -> None:
        self._states: dict[str, TaskMonitorState] = {}

    def upsert_queued(
        self,
        *,
        task_id: str,
        agent_id: str,
        variant_id: str,
        sample_id: str | None,
    ) -> TaskMonitorState:
        key = f"{task_id}::{agent_id}::{variant_id}::{sample_id or '-'}"
        state = self._states.get(key)
        if state is None:
            state = TaskMonitorState(
                task_id=task_id,
                agent_id=agent_id,
                variant_id=variant_id,
                sample_id=sample_id,
            )
            self._states[key] = state
        return state

    def seed_state(
        self,
        *,
        task_id: str,
        agent_id: str,
        variant_id: str,
        sample_id: str | None,
        status: str,
        started_at_ms: int | None = None,
        ended_at_ms: int | None = None,
        duration_ms: int | None = None,
        latest_message: str | None = None,
        scorer_metrics: Mapping[str, float] | None = None,
    ) -> TaskMonitorState:
        state = self.upsert_queued(
            task_id=task_id,
            agent_id=agent_id,
            variant_id=variant_id,
            sample_id=sample_id,
        )
        try:
            state.status = TaskExecutionStatus(str(status or "queued"))
        except Exception:
            state.status = TaskExecutionStatus.QUEUED
        state.started_at_ms = started_at_ms
        state.ended_at_ms = ended_at_ms
        state.duration_ms = duration_ms
        state.latest_message = latest_message
        state.scorer_metrics = {
            str(k): float(v)
            for k, v in dict(scorer_metrics or {}).items()
            if isinstance(v, (int, float))
        }
        return state

    def apply_event(self, event: UIEvent) -> TaskMonitorState | None:
        if not event.task_id or not event.agent_id:
            return None
        state = self.upsert_queued(
            task_id=event.task_id,
            agent_id=event.agent_id,
            variant_id=event.variant_id or "default",
            sample_id=(str(event.payload.get("sample_id")) if event.payload.get("sample_id") is not None else None),
        )
        name = event.event
        state.latest_message = event.message or state.latest_message
        if name == "runtime.trial.start":
            state.status = TaskExecutionStatus.RUNNING
            state.started_at_ms = event.ts_ms
        elif name.startswith("runtime.trial.step"):
            state.step_count += 1
            action = event.payload.get("action") or event.payload.get("action_type")
            obs = event.payload.get("observation") or event.payload.get("observation_type")
            if action is not None:
                state.latest_action = str(action)
            if obs is not None:
                state.latest_observation = str(obs)
        elif name == "runtime.scorer.start":
            state.status = TaskExecutionStatus.SCORING
        elif name == "runtime.scorer.finish":
            metrics = event.payload.get("metrics")
            if isinstance(metrics, dict):
                state.scorer_metrics = {
                    str(k): float(v)
                    for k, v in metrics.items()
                    if isinstance(v, (int, float))
                }
        elif name == "runtime.trial.finish":
            raw_status = str(event.payload.get("status") or event.message or "success")
            try:
                state.status = TaskExecutionStatus(raw_status)
            except Exception:
                state.status = TaskExecutionStatus.SUCCESS
            state.ended_at_ms = event.ts_ms
            if state.started_at_ms is not None:
                state.duration_ms = max(0, state.ended_at_ms - state.started_at_ms)
        elif name == "runtime.trial.error":
            state.status = TaskExecutionStatus.ERROR
            state.ended_at_ms = event.ts_ms
            if state.started_at_ms is not None:
                state.duration_ms = max(0, state.ended_at_ms - state.started_at_ms)
        return state

    def list_states(self) -> list[TaskMonitorState]:
        return sorted(self._states.values(), key=lambda s: (s.task_id, s.agent_id, s.variant_id, s.sample_id or ""))


@dataclass(frozen=True)
class ScoreExplanation:
    metric: str
    value: float
    evidence: list[str] = field(default_factory=list)
    reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def build_score_explanations(
    scores: ScoreMap,
    *,
    trace: Mapping[str, Any] | None = None,
    task_result: Mapping[str, Any] | None = None,
) -> list[ScoreExplanation]:
    out: list[ScoreExplanation] = []
    for metric, score in scores.items():
        evidence: list[str] = []
        metadata = dict(score.metadata or {})
        for key in ("judge_prompt", "judge_system_prompt", "judge_error", "parser_name", "target", "extracted"):
            if key in metadata and metadata.get(key) is not None:
                evidence.append(f"{key}={metadata.get(key)}")
        judge_parsed = metadata.get("judge_parsed")
        if isinstance(judge_parsed, dict):
            evidence.append("judge_parsed=" + ",".join(sorted(str(k) for k in judge_parsed.keys())))
        if trace is not None:
            events = trace.get("trace_events", []) if isinstance(trace, Mapping) else []
            if isinstance(events, list) and events:
                evidence.append(f"trace_events={len(events)}")
        if task_result is not None and isinstance(task_result, Mapping):
            status = task_result.get("status")
            if status is not None:
                evidence.append(f"task_status={status}")

        out.append(
            ScoreExplanation(
                metric=str(metric),
                value=float(score.value),
                evidence=evidence,
                reason=score.explanation,
                raw={"metadata": metadata},
            )
        )
    return out
