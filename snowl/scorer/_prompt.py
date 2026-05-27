"""Shared prompt template rendering for judge scorers.

Framework role:
- Provides `render_judge_prompt()` for interpolating `{variable.path}` placeholders
  in judge prompt templates.
- Used by both ModelAsJudgeJSONScorer and RegexGradeJudgeScorer.

Runtime/usage wiring:
- Called during scoring to build system/user prompts from templates.

Change guardrails:
- Template rendering semantics affect reproducibility; change carefully.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from snowl.errors import SnowlValidationError

_TEMPLATE_RE = re.compile(r"\{([^{}]+)\}")


def _format_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _resolve_path(expr: str, variables: Mapping[str, Any]) -> Any:
    if expr in variables:
        return variables[expr]
    parts = [p for p in expr.split(".") if p]
    if not parts:
        raise KeyError(expr)

    cur: Any = variables
    for part in parts:
        if isinstance(cur, Mapping):
            if part not in cur:
                raise KeyError(expr)
            cur = cur[part]
            continue
        if hasattr(cur, part):
            cur = getattr(cur, part)
            continue
        raise KeyError(expr)
    return cur


def render_judge_prompt(template: str, variables: Mapping[str, Any], *, strict: bool = True) -> str:
    """Render a judge prompt template by interpolating ``{variable.path}`` placeholders.

    Args:
        template: Prompt template with ``{var}`` or ``{nested.path}`` placeholders.
        variables: Dict of available variables for interpolation.
        strict: If True, raise SnowlValidationError on unknown placeholders.
            If False, leave unknown placeholders unchanged.

    Returns:
        Rendered prompt string.
    """
    def _repl(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        try:
            value = _resolve_path(expr, variables)
        except KeyError:
            if strict:
                raise SnowlValidationError(
                    f"Unknown placeholder '{expr}' in judge prompt template."
                )
            return match.group(0)
        return _format_scalar(value)

    return _TEMPLATE_RE.sub(_repl, template)
