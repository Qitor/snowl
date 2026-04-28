"""AgentDojo adapter for non-sandbox tool-safety suites."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import read_json_array, stable_benchmark_id
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


DEFAULT_SUITES = ("banking", "travel")


@dataclass(frozen=True)
class AgentDojoBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = ""
    suite: str = "banking"
    suites: str | list[str] | tuple[str, ...] = field(default_factory=lambda: list(DEFAULT_SUITES))
    rows: list[dict[str, Any]] | None = None
    with_injections: bool | str = True
    name: str = "agentdojo"
    description: str = "AgentDojo benchmark adapter."
    default_split: str = "test"
    stringify_filter_values: bool = False

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name="AgentDojo",
            short_description="Stateful tool-use prompt-injection benchmark",
            domain="agentic_safety",
            benchmark_type="safety",
            family="agentdojo",
            primary_metric="agentdojo_score",
            higher_is_better=True,
            sample_preview_mode="tool_trace",
            dashboard_tags=["prompt_injection", "tool_use", "stateful"],
        )

    def _suite_set(self) -> set[str]:
        raw = self.suites
        if isinstance(raw, str):
            suites = {part.strip() for part in raw.split(",") if part.strip()}
        else:
            suites = {str(part).strip() for part in raw if str(part).strip()}
        suites.add(str(self.suite or "").strip())
        return {suite for suite in suites if suite}

    def _iter_rows(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return [dict(row) for row in self.rows]
        if not self.dataset_path:
            raise SnowlValidationError("AgentDojo requires rows=... or dataset_path=....")
        data = read_json_array(self.dataset_path, not_found_message="AgentDojo dataset not found", invalid_message="AgentDojo dataset must be a JSON array")
        return [dict(row) for row in data if isinstance(row, dict)]

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get("split") or self.default_split)

    def _matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        suite = str(row.get("suite") or row.get("task_suite_name") or "").strip()
        if suite and suite not in self._suite_set():
            return False
        if not _coerce_bool(self.with_injections) and row.get("injection_task_id") is not None:
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
        prompt = str(row.get("prompt") or row.get("input") or row.get("user_task_prompt") or "").strip()
        if not prompt:
            return None
        suite = str(row.get("suite") or row.get("task_suite_name") or self.suite).strip()
        sample_id = str(row.get("id") or "").strip() or stable_benchmark_id("agentdojo", suite, row_index, prompt)
        tools = _tool_schemas(row.get("tools") or row.get("tool_schemas") or _default_suite_tools(suite))
        metadata = {
            "split": row_split,
            "suite": suite,
            "task_suite_name": suite,
            "user_task_id": row.get("user_task_id") or row.get("task_id"),
            "injection_task_id": row.get("injection_task_id"),
            "requires_sandbox": bool(row.get("requires_sandbox", False)),
            "tool_schemas": tools,
            "tool_names": [schema["function"]["name"] for schema in tools if isinstance(schema.get("function"), Mapping)],
            "pre_state": dict(row.get("pre_state") or {}),
            "post_state": dict(row.get("post_state") or {}),
            "state_checks": list(row.get("state_checks") or []),
            "forbidden_tools": list(row.get("forbidden_tools") or []),
            "forbidden_arg_patterns": list(row.get("forbidden_arg_patterns") or []),
        }
        return {"id": sample_id, "input": prompt, "metadata": metadata}

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no"}


def _tool_schemas(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
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
                    "description": str(fn.get("description") or f"Tool {name}."),
                    "parameters": dict(parameters),
                },
            }
        )
    return out


def _default_suite_tools(suite: str) -> list[dict[str, Any]]:
    if suite == "banking":
        names = ("get_balance", "get_transactions", "send_money")
    elif suite == "travel":
        names = ("search_flights", "book_flight", "get_reservation")
    else:
        names = ("read_state", "write_state")
    return [
        {
            "name": name,
            "description": f"{suite} tool {name}.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        }
        for name in names
    ]
