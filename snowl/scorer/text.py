"""Text matching scorers inspired by inspect.ai primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from snowl.core import Score, ScoreContext, TaskResult

from snowl.scorer.base import (
    OutputExtractor,
    SimpleExtractor,
    SimpleTargetExtractor,
    TargetExtractor,
    default_output_extractor,
    default_target_extractor,
    normalize_text,
    run_extractor,
)


@dataclass(frozen=True)
class IncludesScorer:
    metric_name: str = "includes"
    case_sensitive: bool = False
    extract: Callable[..., Any] = default_output_extractor
    target: Callable[..., Any] = default_target_extractor
    scorer_id: str = "includes"

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        output = str(run_extractor(self.extract, task_result, trace, context) or "")
        target_value = run_extractor(self.target, task_result, trace, context)
        target = str(target_value) if target_value is not None else None
        if target is None:
            return {
                self.metric_name: Score(
                    value=0.0,
                    explanation="Missing target in sample/task metadata.",
                    metadata={"matched": False, "target_missing": True},
                )
            }

        left = output if self.case_sensitive else output.lower()
        right = target if self.case_sensitive else target.lower()
        matched = right in left
        return {
            self.metric_name: Score(
                value=1.0 if matched else 0.0,
                explanation=f"Target {'found' if matched else 'not found'} in output.",
                metadata={"matched": matched, "target": target},
            )
        }


@dataclass(frozen=True)
class MatchScorer:
    metric_name: str = "match"
    position: str = "end"
    ignore_case: bool = True
    ignore_whitespace: bool = True
    ignore_punctuation: bool = True
    extract: Callable[..., Any] = default_output_extractor
    target: Callable[..., Any] = default_target_extractor
    scorer_id: str = "match"

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        output = str(run_extractor(self.extract, task_result, trace, context) or "")
        target_value = run_extractor(self.target, task_result, trace, context)
        target = str(target_value) if target_value is not None else None
        if target is None:
            return {
                self.metric_name: Score(
                    value=0.0,
                    explanation="Missing target in sample/task metadata.",
                    metadata={"matched": False, "target_missing": True},
                )
            }

        norm_output = normalize_text(
            output,
            ignore_case=self.ignore_case,
            ignore_whitespace=self.ignore_whitespace,
            ignore_punctuation=self.ignore_punctuation,
        )
        norm_target = normalize_text(
            target,
            ignore_case=self.ignore_case,
            ignore_whitespace=self.ignore_whitespace,
            ignore_punctuation=self.ignore_punctuation,
        )

        position = self.position.strip().lower()
        if position not in {"start", "end"}:
            position = "end"

        matched = (
            norm_output.startswith(norm_target)
            if position == "start"
            else norm_output.endswith(norm_target)
        )
        return {
            self.metric_name: Score(
                value=1.0 if matched else 0.0,
                explanation=f"Target {'matches' if matched else 'does not match'} {position}.",
                metadata={"matched": matched, "position": position, "target": target},
            )
        }


@dataclass(frozen=True)
class PatternScorer:
    pattern: str
    group: int | str = 0
    flags: int = 0
    metric_name: str = "pattern"
    case_sensitive: bool = False
    extract: Callable[..., Any] = default_output_extractor
    target: Callable[..., Any] = default_target_extractor
    scorer_id: str = "pattern"

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        output = str(run_extractor(self.extract, task_result, trace, context) or "")
        target_value = run_extractor(self.target, task_result, trace, context)
        target = str(target_value) if target_value is not None else None
        try:
            compiled = re.compile(self.pattern, self.flags)
        except re.error as exc:
            return {
                self.metric_name: Score(
                    value=0.0,
                    explanation=f"Invalid regex pattern: {exc}",
                    metadata={"matched": False, "regex_error": str(exc)},
                )
            }

        match = compiled.search(output)
        if match is None:
            return {
                self.metric_name: Score(
                    value=0.0,
                    explanation="Pattern not found in output.",
                    metadata={"matched": False, "extracted": None},
                )
            }

        extracted = match.group(self.group)
        if target is None:
            return {
                self.metric_name: Score(
                    value=1.0,
                    explanation="Pattern matched and extracted value.",
                    metadata={"matched": True, "extracted": extracted, "target_missing": True},
                )
            }

        left = extracted if self.case_sensitive else extracted.lower()
        right = target if self.case_sensitive else target.lower()
        ok = left == right
        return {
            self.metric_name: Score(
                value=1.0 if ok else 0.0,
                explanation=f"Extracted value {'matches' if ok else 'does not match'} target.",
                metadata={"matched": ok, "extracted": extracted, "target": target},
            )
        }


def includes(
    *,
    case_sensitive: bool = False,
    metric_name: str = "includes",
    extract: SimpleExtractor | OutputExtractor = default_output_extractor,
    target: SimpleTargetExtractor | TargetExtractor = default_target_extractor,
    output_extractor: OutputExtractor | None = None,
    target_extractor: TargetExtractor | None = None,
) -> IncludesScorer:
    if output_extractor is not None:
        extract = output_extractor
    if target_extractor is not None:
        target = target_extractor
    return IncludesScorer(
        metric_name=metric_name,
        case_sensitive=case_sensitive,
        extract=extract,
        target=target,
    )


def match(
    *,
    position: str = "end",
    ignore_case: bool = True,
    ignore_whitespace: bool = True,
    ignore_punctuation: bool = True,
    metric_name: str = "match",
    extract: SimpleExtractor | OutputExtractor = default_output_extractor,
    target: SimpleTargetExtractor | TargetExtractor = default_target_extractor,
    output_extractor: OutputExtractor | None = None,
    target_extractor: TargetExtractor | None = None,
) -> MatchScorer:
    if output_extractor is not None:
        extract = output_extractor
    if target_extractor is not None:
        target = target_extractor
    return MatchScorer(
        metric_name=metric_name,
        position=position,
        ignore_case=ignore_case,
        ignore_whitespace=ignore_whitespace,
        ignore_punctuation=ignore_punctuation,
        extract=extract,
        target=target,
    )


def pattern(
    regex: str,
    *,
    group: int | str = 0,
    flags: int = 0,
    metric_name: str = "pattern",
    case_sensitive: bool = False,
    extract: SimpleExtractor | OutputExtractor = default_output_extractor,
    target: SimpleTargetExtractor | TargetExtractor = default_target_extractor,
    output_extractor: OutputExtractor | None = None,
    target_extractor: TargetExtractor | None = None,
) -> PatternScorer:
    if output_extractor is not None:
        extract = output_extractor
    if target_extractor is not None:
        target = target_extractor
    return PatternScorer(
        pattern=regex,
        group=group,
        flags=flags,
        metric_name=metric_name,
        case_sensitive=case_sensitive,
        extract=extract,
        target=target,
    )
