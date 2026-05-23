"""Berkeley function-calling benchmark adapter."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import read_json_array, stable_benchmark_id
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


DEFAULT_CATEGORIES = ("simple_python", "multiple", "parallel", "parallel_multiple", "irrelevance")


@dataclass(frozen=True)
class BFCLBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = ""
    categories: str | list[str] | tuple[str, ...] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    rows: list[dict[str, Any]] | None = None
    name: str = "bfcl"
    description: str = "Function-calling benchmark adapter."
    default_split: str = "test"
    stringify_filter_values: bool = False

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name="BFCL",
            short_description="Function-calling accuracy benchmark",
            domain="agentic_capability",
            benchmark_type="capability",
            family="bfcl",
            primary_metric="function_call_accuracy",
            higher_is_better=True,
            sample_preview_mode="tool_trace",
            dashboard_tags=["function_calling", "tool_use"],
        )

    def _category_set(self) -> set[str]:
        raw = self.categories
        if isinstance(raw, str):
            return {part.strip() for part in raw.split(",") if part.strip()}
        return {str(part).strip() for part in raw if str(part).strip()}

    def _iter_rows(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return [dict(row) for row in self.rows]
        if not self.dataset_path:
            raise SnowlValidationError("BFCL requires rows=... or dataset_path=....")
        path = Path(self.dataset_path)
        if path.is_dir():
            rows: list[dict[str, Any]] = []
            for file in sorted(path.glob("*.json")):
                data = read_json_array(file, not_found_message="BFCL data file not found", invalid_message="BFCL data file must be a JSON array")
                category = file.stem.replace("BFCL_v3_", "").replace("BFCL_v2_", "").replace("BFCL_v1_", "")
                for row in data:
                    if isinstance(row, dict):
                        rows.append({**row, "category_name": row.get("category_name") or category})
            return rows
        data = read_json_array(path, not_found_message="BFCL dataset not found", invalid_message="BFCL dataset must be a JSON array")
        return [dict(row) for row in data if isinstance(row, dict)]

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get("split") or self.default_split)

    def _matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        category = str(row.get("category_name") or row.get("category") or "").strip()
        if category and category not in self._category_set():
            return False
        return super()._matches_filters(row, filters)

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = selected_count
        category = str(row.get("category_name") or row.get("category") or "simple_python").strip()
        question_turns = row.get("question") or row.get("messages") or []
        messages = _single_turn_messages(question_turns)
        if not messages:
            return None
        tools = _tool_schemas(row.get("function") or row.get("tools") or [])
        expected = _expected_calls(row.get("ground_truth") or row.get("parsed_ground_truth") or [])
        mode = _mode_for_category(category)
        sample_id = str(row.get("id") or "").strip() or stable_benchmark_id("bfcl", category, messages)
        return {
            "id": sample_id,
            "messages": messages,
            "metadata": {
                "split": row_split,
                "category_name": category,
                "function_call_mode": mode,
                "tools": tools,
                "tool_schemas": tools,
                "tool_names": [schema["function"]["name"] for schema in tools if isinstance(schema.get("function"), Mapping)],
                "raw_ground_truth": row.get("ground_truth"),
                "parsed_ground_truth": expected,
                "expected_tool_calls": expected,
            },
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")


def _mode_for_category(category: str) -> str:
    if "irrelevance" in category:
        return "irrelevance"
    if "relevance" in category:
        return "relevance"
    return "match"


def _single_turn_messages(question: Any) -> list[dict[str, str]]:
    if isinstance(question, str):
        return [{"role": "user", "content": question}]
    if isinstance(question, Sequence) and not isinstance(question, (str, bytes, bytearray)):
        if question and isinstance(question[0], Sequence) and not isinstance(question[0], Mapping):
            first_turn = question[0]
        else:
            first_turn = question
        messages: list[dict[str, str]] = []
        for item in first_turn:
            if isinstance(item, Mapping):
                messages.append({"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")})
        return messages
    return []


def _tool_schemas(raw_tools: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, (str, bytes, bytearray)):
        return []
    out: list[dict[str, Any]] = []
    for item in raw_tools:
        if not isinstance(item, Mapping):
            continue
        fn = item.get("function") if isinstance(item.get("function"), Mapping) else item
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        parameters = fn.get("parameters")
        if not isinstance(parameters, Mapping):
            parameters = {"type": "object", "properties": {}, "additionalProperties": False}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(fn.get("description") or f"Function {name}."),
                    "parameters": dict(parameters),
                },
            }
        )
    return out


def _expected_calls(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raw = [raw]
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping):
            if "name" in item:
                out.append({"name": str(item.get("name") or ""), "arguments": dict(item.get("arguments") or {})})
            else:
                for name, args in item.items():
                    values = args
                    if isinstance(args, Mapping):
                        values = {key: _first_possible(value) for key, value in args.items()}
                    out.append({"name": str(name), "arguments": dict(values) if isinstance(values, Mapping) else {}})
        elif isinstance(item, str):
            parsed = _parse_call_string(item)
            if parsed:
                out.append(parsed)
    return [item for item in out if item.get("name")]


def _first_possible(value: Any) -> Any:
    if isinstance(value, list) and value:
        return value[0]
    return value


def _parse_call_string(text: str) -> dict[str, Any] | None:
    try:
        expr = ast.parse(text.strip(), mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(expr, ast.Call):
        return None
    name = expr.func.id if isinstance(expr.func, ast.Name) else ""
    args: dict[str, Any] = {}
    for kw in expr.keywords:
        if kw.arg:
            try:
                args[kw.arg] = ast.literal_eval(kw.value)
            except Exception:
                args[kw.arg] = ast.unparse(kw.value)
    return {"name": name, "arguments": args} if name else None
