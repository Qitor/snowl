"""Shared utilities for built-in scorers."""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from snowl.core import ScoreContext, TaskResult

OutputExtractor = Callable[[TaskResult, Mapping[str, Any], ScoreContext], str]
TargetExtractor = Callable[[TaskResult, Mapping[str, Any], ScoreContext], str | None]
SimpleExtractor = Callable[[TaskResult], Any]
SimpleTargetExtractor = Callable[[TaskResult], Any]


def default_output_extractor(
    task_result: TaskResult,
    trace: Mapping[str, Any],
    context: ScoreContext,
) -> str:
    _ = (trace, context)
    content = task_result.final_output.get("content")
    if content is None:
        message = task_result.final_output.get("message")
        if isinstance(message, Mapping):
            content = message.get("content")
    return str(content or "")


def default_target_extractor(
    task_result: TaskResult,
    trace: Mapping[str, Any],
    context: ScoreContext,
) -> str | None:
    _ = (task_result, trace)
    for key in ("target", "answer", "expected"):
        value = context.sample_metadata.get(key)
        if value is not None:
            return str(value)
    for key in ("target", "answer", "expected"):
        value = context.task_metadata.get(key)
        if value is not None:
            return str(value)
    return None


def run_extractor(
    fn: Callable[..., Any],
    task_result: TaskResult,
    trace: Mapping[str, Any],
    context: ScoreContext,
) -> Any:
    """Run extractor in a backward-compatible way.

    Preferred user style: lambda tr: ...
    Also supports advanced style: fn(task_result, trace, context).
    """
    try:
        return fn(task_result)
    except TypeError:
        return fn(task_result, trace, context)


def normalize_text(
    text: str,
    *,
    ignore_case: bool = True,
    ignore_whitespace: bool = False,
    ignore_punctuation: bool = False,
) -> str:
    out = text
    if ignore_case:
        out = out.lower()
    if ignore_whitespace:
        out = re.sub(r"\s+", "", out)
    if ignore_punctuation:
        out = re.sub(r"[^\w\s]", "", out)
    return out
