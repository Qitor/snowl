"""AgentDojo adapter for non-sandbox tool-safety suites."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import read_json_array, stable_benchmark_id
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


DEFAULT_SUITES = ("banking", "travel")


def _default_assets_dir() -> Path:
    """Resolve the AgentDojo assets directory within the snowl repo."""
    # snowl/benchmarks/agentdojo/adapter.py -> snowl root
    return Path(__file__).resolve().parents[3] / "references" / "AgentDojo" / "assets"


@dataclass(frozen=True)
class AgentDojoBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = ""

    @classmethod
    def default_dataset_path(cls) -> str:
        """Return the default path to the generated AgentDojo dataset."""
        p = _default_assets_dir() / "all_cases.json"
        return str(p)
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
            middleware_hints={"type": "stateful", "suite": self.suite},
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
        path = self.dataset_path or self.default_dataset_path()
        data = read_json_array(path, not_found_message="AgentDojo dataset not found", invalid_message="AgentDojo dataset must be a JSON array")
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
        injection_task_id = row.get("injection_task_id")
        attack_type = row.get("attack_type")
        tools = _tool_schemas(row.get("tools") or row.get("tool_schemas") or _default_suite_tools(suite))
        user_task_id = str(row.get("user_task_id") or row.get("task_id") or "")
        metadata = {
            "split": row_split,
            "suite": suite,
            "task_suite_name": suite,
            "user_task_id": user_task_id,
            "injection_task_id": injection_task_id,
            "requires_sandbox": bool(row.get("requires_sandbox", False)),
            "tool_schemas": tools,
            "tool_names": [schema["function"]["name"] for schema in tools if isinstance(schema.get("function"), Mapping)],
            "pre_state": dict(row.get("pre_state") or {}),
            "post_state": dict(row.get("post_state") or {}),
            "state_checks": list(row.get("state_checks") or []),
            "user_utility_checks": list(row.get("user_utility_checks") or []),
            "attack_success_post_state": dict(row.get("attack_success_post_state") or {}),
            "attack_success_checks": list(row.get("attack_success_checks") or []),
            "ground_truth_output": str(row.get("ground_truth_output") or ""),
            "forbidden_tools": list(row.get("forbidden_tools") or []),
            "forbidden_arg_patterns": list(row.get("forbidden_arg_patterns") or []),
        }

        # Paired evaluation metadata
        is_attacked = injection_task_id is not None
        pair_key = f"{suite}::{user_task_id}"
        if is_attacked:
            pair_key += f"::{injection_task_id}::{attack_type}"
        metadata["pair_id"] = pair_key
        metadata["run_mode"] = "attacked" if is_attacked else "clean"

        # Injection config for InjectionMiddleware (only for attacked samples)
        attack_string = row.get("attack_string", "")
        if attack_string:
            metadata["injection_config"] = {
                "injection_string": attack_string,
                "position": row.get("injection_position", "append"),
                "target_field": row.get("injection_target_field"),
                "target_tools": row.get("injection_target_tools"),
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
    """Load tool schemas from the generated JSON files, falling back to stubs."""
    schema_path = _default_assets_dir() / f"{suite}_tools.json"
    if schema_path.exists():
        try:
            with open(schema_path) as f:
                schemas = json.load(f)
            if isinstance(schemas, list) and schemas:
                return schemas
        except (json.JSONDecodeError, OSError):
            pass
    # Fallback stubs
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
