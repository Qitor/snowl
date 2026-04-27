"""Regex-grade LLM judge scorer primitives."""

from __future__ import annotations

import asyncio
import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from snowl.core import Score, ScoreContext, TaskResult
from snowl.errors import SnowlValidationError
from snowl.model import ChatModelClient
from snowl.scorer.base import default_output_extractor, run_extractor

JudgeClientFactory = Callable[[str], ChatModelClient]


def _run_coro_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result_box["result"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive
            error_box["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("result")


_TEMPLATE_RE = re.compile(r"\{([^{}]+)\}")


def _resolve(expr: str, variables: Mapping[str, Any]) -> Any:
    if expr in variables:
        return variables[expr]
    cur: Any = variables
    for part in [p for p in expr.split(".") if p]:
        if isinstance(cur, Mapping) and part in cur:
            cur = cur[part]
        elif hasattr(cur, part):
            cur = getattr(cur, part)
        else:
            raise KeyError(expr)
    return cur


def _format(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render_prompt_template(template: str, variables: Mapping[str, Any], *, strict: bool = True) -> str:
    def repl(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        try:
            return _format(_resolve(expr, variables))
        except KeyError:
            if strict:
                raise SnowlValidationError(f"Unknown placeholder '{expr}' in judge prompt.")
            return match.group(0)

    return _TEMPLATE_RE.sub(repl, template)


def _response_content(response: Any) -> str:
    if hasattr(response, "message"):
        message = getattr(response, "message")
        if isinstance(message, Mapping):
            return str(message.get("content", ""))
        return str(message)
    if isinstance(response, Mapping):
        message = response.get("message")
        if isinstance(message, Mapping):
            return str(message.get("content", ""))
        if response.get("content") is not None:
            return str(response.get("content"))
    return str(response)


@dataclass(frozen=True)
class JudgeGrade:
    model_name: str
    raw_output: str
    grade: str | None
    score_value: float | None
    explanation: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class MultiJudgeReducer:
    tie_break: str = "max"
    invalid_policy: str = "drop"

    def reduce(self, grades: list[JudgeGrade]) -> tuple[float, str | None, dict[str, Any]]:
        valid = [g for g in grades if g.score_value is not None and g.grade is not None]
        if not valid:
            return 0.0, "No valid judge grades.", {"valid_count": 0, "judges": [g.__dict__ for g in grades]}
        values = [float(g.score_value) for g in valid]
        if self.tie_break == "majority_label":
            counts: dict[str, int] = {}
            for grade in valid:
                counts[str(grade.grade)] = counts.get(str(grade.grade), 0) + 1
            best_count = max(counts.values())
            winners = [label for label, count in counts.items() if count == best_count]
            winner = sorted(winners)[0]
            winner_values = [float(g.score_value) for g in valid if g.grade == winner]
            value = sum(winner_values) / len(winner_values)
            explanation = f"majority label {winner} from {len(valid)} valid judges"
        elif self.tie_break == "max":
            value = max(values)
            explanation = f"max score from {len(valid)} valid judges"
        else:
            value = sum(values) / len(values)
            explanation = f"mean score from {len(valid)} valid judges"
        return value, explanation, {"valid_count": len(valid), "judges": [g.__dict__ for g in grades]}


@dataclass
class RegexGradeJudgeScorer:
    model_names: list[str]
    system_prompt: str
    user_prompt: str
    grade_pattern: str
    label_to_score: dict[str, float]
    metric_name: str = "judge"
    output_extractor: Any = default_output_extractor
    reducer: MultiJudgeReducer = field(default_factory=MultiJudgeReducer)
    strict: bool = False
    strict_templates: bool = True
    client_factory: JudgeClientFactory | None = None
    clients: dict[str, ChatModelClient] = field(default_factory=dict)
    scorer_id: str = "regex_grade_judge"

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        variables = self._variables(task_result, trace, context)
        grades: list[JudgeGrade] = []
        try:
            system_prompt = render_prompt_template(
                self.system_prompt,
                variables,
                strict=self.strict_templates,
            )
            user_prompt = render_prompt_template(
                self.user_prompt,
                variables,
                strict=self.strict_templates,
            )
        except Exception as exc:
            if self.strict:
                raise
            return {
                self.metric_name: Score(
                    value=0.0,
                    explanation=f"judge_template_error: {exc}",
                    metadata={"judge_error": str(exc)},
                )
            }

        for model_name in self.model_names:
            grades.append(self._grade_one(model_name, system_prompt, user_prompt))
        value, explanation, metadata = self.reducer.reduce(grades)
        metadata.update(
            {
                "judge_system_prompt": system_prompt,
                "judge_prompt": user_prompt,
                "grade_pattern": self.grade_pattern,
            }
        )
        return {
            self.metric_name: Score(
                value=max(0.0, min(1.0, float(value))),
                explanation=explanation,
                metadata=metadata,
            )
        }

    def _variables(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Any]:
        output = str(run_extractor(self.output_extractor, task_result, trace, context) or "")
        variables: dict[str, Any] = {
            "output": output,
            "answer": output,
            "payload": dict(task_result.payload),
            "task_result": task_result.to_dict(),
            "trace": dict(trace),
            "context": {
                "task_id": context.task_id,
                "agent_id": context.agent_id,
                "sample_id": context.sample_id,
                "task_metadata": dict(context.task_metadata),
                "sample_metadata": dict(context.sample_metadata),
            },
            "metadata": dict(context.sample_metadata),
            "task_metadata": dict(context.task_metadata),
        }
        variables.update(dict(task_result.payload))
        variables.update(dict(context.sample_metadata))
        return variables

    def _client(self, model_name: str) -> ChatModelClient:
        if model_name in self.clients:
            return self.clients[model_name]
        if self.client_factory is None:
            raise SnowlValidationError("RegexGradeJudgeScorer requires client_factory or clients.")
        client = self.client_factory(model_name)
        self.clients[model_name] = client
        return client

    def _grade_one(self, model_name: str, system_prompt: str, user_prompt: str) -> JudgeGrade:
        raw = ""
        try:
            response = _run_coro_sync(
                self._client(model_name).generate(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    model=model_name,
                )
            )
            raw = _response_content(response)
            match = re.search(self.grade_pattern, raw)
            if not match:
                return JudgeGrade(model_name=model_name, raw_output=raw, grade=None, score_value=None, error="grade_not_found")
            grade = str(match.group(1)).strip()
            key = grade.upper()
            value = self.label_to_score.get(key)
            if value is None:
                return JudgeGrade(model_name=model_name, raw_output=raw, grade=grade, score_value=None, error="unknown_grade")
            explanation = raw[: match.start()].strip() or None
            return JudgeGrade(
                model_name=model_name,
                raw_output=raw,
                grade=grade,
                score_value=float(value),
                explanation=explanation,
            )
        except Exception as exc:
            if self.strict:
                raise
            return JudgeGrade(model_name=model_name, raw_output=raw, grade=None, score_value=None, error=str(exc))


def regex_grade_judge(
    *,
    model_name: str | list[str],
    system_prompt: str,
    user_prompt: str,
    grade_pattern: str,
    label_to_score: dict[str, float],
    metric_name: str = "judge",
    client_factory: JudgeClientFactory | None = None,
) -> RegexGradeJudgeScorer:
    models = [model_name] if isinstance(model_name, str) else list(model_name)
    return RegexGradeJudgeScorer(
        model_names=models,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        grade_pattern=grade_pattern,
        label_to_score={str(k).upper(): float(v) for k, v in label_to_score.items()},
        metric_name=metric_name,
        client_factory=client_factory,
    )
