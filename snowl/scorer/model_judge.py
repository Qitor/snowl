"""Model-as-a-judge JSON scorer."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from snowl.core import Score, ScoreContext, TaskResult
from snowl.errors import SnowlValidationError
from snowl.model import ChatModelClient

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

    import threading

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("result")


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


def _render_template(template: str, variables: Mapping[str, Any], *, strict: bool) -> str:
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


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise SnowlValidationError("Judge output does not contain a JSON object.")
    obj = json.loads(stripped[start : end + 1])
    if not isinstance(obj, dict):
        raise SnowlValidationError("Judge output JSON must be an object.")
    return obj


def _validate_schema(payload: Any, schema: dict[str, Any], path: str = "$") -> None:
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(payload, dict):
            raise SnowlValidationError(f"Schema violation at {path}: expected object.")
        required = schema.get("required", [])
        for key in required:
            if key not in payload:
                raise SnowlValidationError(f"Schema violation at {path}: missing '{key}'.")
        properties = schema.get("properties", {})
        for key, value in payload.items():
            if key in properties:
                _validate_schema(value, properties[key], f"{path}.{key}")
            elif schema.get("additionalProperties", True) is False:
                raise SnowlValidationError(f"Schema violation at {path}: unexpected field '{key}'.")
        return

    if schema_type == "array":
        if not isinstance(payload, list):
            raise SnowlValidationError(f"Schema violation at {path}: expected array.")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(payload):
                _validate_schema(item, item_schema, f"{path}[{i}]")
        return

    if schema_type == "string" and not isinstance(payload, str):
        raise SnowlValidationError(f"Schema violation at {path}: expected string.")
    if schema_type == "number" and not isinstance(payload, (int, float)):
        raise SnowlValidationError(f"Schema violation at {path}: expected number.")
    if schema_type == "integer" and not isinstance(payload, int):
        raise SnowlValidationError(f"Schema violation at {path}: expected integer.")
    if schema_type == "boolean" and not isinstance(payload, bool):
        raise SnowlValidationError(f"Schema violation at {path}: expected boolean.")


@dataclass
class ModelAsJudgeJSONScorer:
    model_name: str
    system_prompt_template: str
    user_prompt_template: str
    schema: dict[str, Any] | None = None
    metric_name: str = "judge"
    score_field: str = "score"
    explanation_field: str = "reasoning"
    strict: bool = False
    strict_templates: bool = True
    client: ChatModelClient | None = None
    client_factory: JudgeClientFactory | None = None
    scorer_id: str = "model_as_judge_json"

    def _get_client(self) -> ChatModelClient:
        if self.client is not None:
            return self.client
        if self.client_factory is None:
            raise SnowlValidationError(
                "model_as_judge_json requires `client` or `client_factory`."
            )
        self.client = self.client_factory(self.model_name)
        return self.client

    def _build_template_variables(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Any]:
        tr = task_result.to_dict()
        ctx = asdict(context)
        payload = dict(task_result.payload)
        output = task_result.final_output.get("content")
        if output is None:
            message = task_result.final_output.get("message")
            if isinstance(message, Mapping):
                output = message.get("content")
        target = None
        for key in ("target", "answer", "expected"):
            value = context.sample_metadata.get(key)
            if value is not None:
                target = str(value)
                break
        if target is None:
            for key in ("target", "answer", "expected"):
                value = context.task_metadata.get(key)
                if value is not None:
                    target = str(value)
                    break
        variables: dict[str, Any] = {
            "task_result": tr,
            "payload": payload,
            "context": ctx,
            "trace": dict(trace),
            "output": str(output or ""),
            "target": target,
            "schema": self.schema or {},
            "schema_json": json.dumps(self.schema or {}, ensure_ascii=False, indent=2),
        }
        for key, value in tr.items():
            variables.setdefault(key, value)
        for key, value in payload.items():
            variables.setdefault(key, value)
        for key, value in ctx.items():
            variables.setdefault(key, value)
        return variables

    def _extract_content(self, response: Any) -> str:
        if hasattr(response, "message"):
            message = getattr(response, "message")
            if isinstance(message, Mapping):
                return str(message.get("content", ""))
            return str(message)
        if isinstance(response, Mapping):
            message = response.get("message")
            if isinstance(message, Mapping):
                return str(message.get("content", ""))
            content = response.get("content")
            if content is not None:
                return str(content)
        return str(response)

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        variables = self._build_template_variables(task_result, trace, context)
        system_prompt = _render_template(
            self.system_prompt_template,
            variables,
            strict=self.strict_templates,
        )
        user_prompt = _render_template(
            self.user_prompt_template,
            variables,
            strict=self.strict_templates,
        )
        client = self._get_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        raw_text = ""
        parsed: dict[str, Any] | None = None
        try:
            response = _run_coro_sync(client.generate(messages, model=self.model_name))
            raw_text = self._extract_content(response)
            parsed = _extract_json_object(raw_text)
            if self.schema is not None:
                _validate_schema(parsed, self.schema)
            score_value = float(parsed[self.score_field])
            explanation = str(parsed.get(self.explanation_field, "")).strip() or None
            return {
                self.metric_name: Score(
                    value=score_value,
                    explanation=explanation,
                    metadata={
                        "judge_model": self.model_name,
                        "judge_system_prompt": system_prompt,
                        "judge_prompt": user_prompt,
                        "judge_raw_output": raw_text,
                        "judge_parsed": parsed,
                    },
                )
            }
        except Exception as exc:
            if self.strict:
                raise
            return {
                self.metric_name: Score(
                    value=0.0,
                    explanation=f"judge_error: {exc}",
                    metadata={
                        "judge_model": self.model_name,
                        "judge_system_prompt": system_prompt,
                        "judge_prompt": user_prompt,
                        "judge_raw_output": raw_text,
                        "judge_parsed": parsed,
                        "judge_error": str(exc),
                    },
                )
            }


def model_as_judge_json(
    *,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any] | None = None,
    metric_name: str = "judge",
    score_field: str = "score",
    explanation_field: str = "reasoning",
    strict: bool = False,
    strict_templates: bool = True,
    client: ChatModelClient | None = None,
    client_factory: JudgeClientFactory | None = None,
) -> ModelAsJudgeJSONScorer:
    return ModelAsJudgeJSONScorer(
        model_name=model_name,
        system_prompt_template=system_prompt,
        user_prompt_template=user_prompt,
        schema=schema,
        metric_name=metric_name,
        score_field=score_field,
        explanation_field=explanation_field,
        strict=strict,
        strict_templates=strict_templates,
        client=client,
        client_factory=client_factory,
    )
