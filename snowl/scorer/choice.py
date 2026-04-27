"""Multiple-choice answer extraction and scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from snowl.core import Score, ScoreContext, TaskResult
from snowl.scorer.base import default_output_extractor, run_extractor


_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True)
class ChoiceAnswerScorer:
    metric_name: str = "accuracy"
    output_extractor: Any = default_output_extractor
    target_keys: tuple[str, ...] = ("target", "answer", "expected")
    scorer_id: str = "choice_answer"

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        output = str(run_extractor(self.output_extractor, task_result, trace, context) or "")
        choices = context.sample_metadata.get("choices") or []
        target = self._target(context)
        predicted = extract_choice_answer(output, len(choices) if isinstance(choices, list) else 0)
        targets = normalize_choice_targets(target)
        ok = predicted is not None and predicted in targets
        return {
            self.metric_name: Score(
                value=1.0 if ok else 0.0,
                explanation=f"Predicted: {predicted}; target: {sorted(targets)}",
                metadata={"predicted": predicted, "target": target, "targets": sorted(targets)},
            )
        }

    def _target(self, context: ScoreContext) -> Any:
        for key in self.target_keys:
            if key in context.sample_metadata:
                return context.sample_metadata[key]
        for key in self.target_keys:
            if key in context.task_metadata:
                return context.task_metadata[key]
        return None


def extract_choice_answer(output: str, num_choices: int = 0) -> str | None:
    upper = output.strip().upper()
    if not upper:
        return None
    max_letters = _LETTERS[:num_choices] if num_choices > 0 else _LETTERS

    patterns = [
        r"(?:FINAL\s+)?ANSWER\s*[:：]\s*\(?([A-Z])\)?",
        r"THE\s+ANSWER\s+IS\s+\(?([A-Z])\)?",
        r"OPTION\s+\(?([A-Z])\)?",
        r"^\s*\(?([A-Z])\)?\s*$",
    ]
    for pattern in patterns:
        m = re.search(pattern, upper)
        if m and m.group(1) in max_letters:
            return m.group(1)

    last = upper.splitlines()[-1].strip()
    for char in last:
        if char in max_letters:
            return char
    return None


def normalize_choice_targets(target: Any) -> set[str]:
    if target is None:
        return set()
    if isinstance(target, (list, tuple, set)):
        out: set[str] = set()
        for item in target:
            out.update(normalize_choice_targets(item))
        return out
    if isinstance(target, int):
        return {_LETTERS[target]} if 0 <= target < len(_LETTERS) else set()
    raw = str(target).strip().upper()
    if not raw:
        return set()
    if raw.isdigit():
        idx = int(raw)
        return {_LETTERS[idx]} if 0 <= idx < len(_LETTERS) else set()
    return {char for char in raw if char in _LETTERS}


def choice_answer(*, metric_name: str = "accuracy") -> ChoiceAnswerScorer:
    return ChoiceAnswerScorer(metric_name=metric_name)
