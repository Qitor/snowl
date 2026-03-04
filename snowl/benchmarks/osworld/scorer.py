"""OSWorld benchmark-specific scorer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from snowl.core import Score, ScoreContext, TaskResult


def _coerce_score(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


@dataclass
class OSWorldScorer:
    metric_name: str = "accuracy"
    scorer_id: str = "osworld"

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        _ = context
        score_value = _coerce_score(task_result.payload.get("osworld_score"))
        if score_value is None:
            for event in trace.get("trace_events", []):
                if not isinstance(event, Mapping):
                    continue
                if str(event.get("event")) != "osworld.evaluate":
                    continue
                score_value = _coerce_score(event.get("score"))
                if score_value is not None:
                    break
        if score_value is None:
            text = str(task_result.final_output.get("content") or "").lower()
            if "done" in text and "fail" not in text:
                score_value = 1.0
            elif "success" in text:
                score_value = 1.0
            elif "fail" in text:
                score_value = 0.0
            else:
                score_value = 0.0

        score_value = max(0.0, min(1.0, float(score_value)))
        return {
            self.metric_name: Score(
                value=score_value,
                explanation=f"osworld score={score_value:.3f}",
                metadata={"osworld_score": score_value},
            ),
            "osworld_score": Score(value=score_value, explanation=f"{score_value:.3f}"),
        }


def osworld() -> OSWorldScorer:
    return OSWorldScorer()

