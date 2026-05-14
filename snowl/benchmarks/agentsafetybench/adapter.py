"""Adapter layer that maps `agentsafetybench` source datasets into Snowl task/sample contracts.

Framework role:
- Owns benchmark-specific split/filter/sample-id logic and metadata extraction.
- Keeps shared runtime generic by normalizing benchmark rows into standard task inputs.

Runtime/usage wiring:
- Loaded by benchmark registry/bench orchestration and executed through the shared eval pipeline.
- Key top-level symbols in this file: `_default_dataset_path`, `AgentSafetyBenchBenchmarkAdapter`.

Change guardrails:
- Preserve deterministic sample identity and metadata contract; scorer/runtime layers depend on it.
- Must not import from the Agent-SafetyBench Python package.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import default_reference_path, read_json_array, stable_benchmark_id
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


def _default_dataset_path() -> str:
    return default_reference_path(
        __file__,
        "Agent-SafetyBench",
        "data",
        "released_data.json",
    )


def _default_env_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "references" / "Agent-SafetyBench" / "environments"


@lru_cache(maxsize=512)
def _cached_load_tool_schemas(env_name: str, tool_names_key: str, env_dir: str) -> list[dict[str, Any]]:
    """Cache tool schema loading to avoid re-reading .json files for shared environments."""
    from snowl.benchmarks.agentsafetybench.env_loader import load_tool_schemas
    tool_names = tool_names_key.split(",") if tool_names_key else None
    return load_tool_schemas(env_name, env_dir, tool_names)


@dataclass(frozen=True)
class AgentSafetyBenchBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = _default_dataset_path()
    name: str = "agentsafetybench"
    description: str = "Agent-SafetyBench benchmark adapter."
    default_split: str = "official"
    env_dir: str = ""

    def _get_env_dir(self) -> str:
        return self.env_dir or str(_default_env_dir())

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name="Agent-SafetyBench",
            short_description="LLM agent safety benchmark with tool-use environments",
            domain="agentic_safety",
            benchmark_type="safety",
            family="agentsafetybench",
            primary_metric="agentsafetybench_safety",
            higher_is_better=True,
            sample_preview_mode="tool_trace",
            dashboard_tags=["agent_safety", "tool_use", "stateful"],
            middleware_hints={"type": "agentsafetybench", "execution_mode": "dynamic_env"},
        )

    def list_splits(self) -> list[str]:
        return [self.default_split]

    def _iter_rows(self) -> list[dict[str, Any]]:
        data = read_json_array(
            self.dataset_path,
            not_found_message="Agent-SafetyBench dataset file not found",
            invalid_message="Agent-SafetyBench dataset must be a JSON array",
        )
        rows = [dict(item) for item in data if isinstance(item, dict)]
        if not rows:
            raise SnowlValidationError(
                f"No Agent-SafetyBench rows found in dataset: {self.dataset_path}"
            )
        return rows

    def _validate_split_request(self, split: str) -> None:
        if split != self.default_split:
            raise SnowlValidationError(
                f"Agent-SafetyBench only exposes split '{self.default_split}', got '{split}'."
            )

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = (row, row_index)
        return self.default_split

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = (row_index, selected_count)
        instruction = str(row.get("instruction") or "").strip()
        if not instruction:
            return None
        sample_id = f"agentsafetybench-{row.get('id')}"

        # Resolve tool schemas from environment .json files
        environments = list(row.get("environments") or [])
        has_environments = bool(environments) and any(e.get("name", "") != "" for e in environments)
        tool_schemas: list[dict[str, Any]] = []
        tool_names: list[str] = []

        env_dir = self._get_env_dir()
        if has_environments:
            for env_info in environments:
                env_name = env_info.get("name", "")
                if not env_name:
                    continue
                env_tool_names = env_info.get("tools") or []
                # Cache key: env_name + sorted tool names
                tool_names_key = ",".join(sorted(env_tool_names))
                schemas = _cached_load_tool_schemas(env_name, tool_names_key, env_dir)
                tool_schemas.extend(schemas)
                tool_names.extend(env_tool_names)

        # Extract dialog for multi-turn samples
        dialog = list(row.get("dialog") or []) if "dialog" in row else []

        return {
            "id": sample_id,
            "input": instruction,
            "metadata": {
                "benchmark": self.name,
                "split": row_split,
                "case": dict(row),
                "case_id": row.get("id"),
                "risks": list(row.get("risks") or []),
                "failure_modes": str(row.get("failure_modes") or ""),
                "fulfillable": row.get("fulfillable"),
                "environments": environments,
                "has_environments": has_environments,
                "tool_schemas": tool_schemas,
                "tool_names": tool_names,
                "dialog": dialog,
            },
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")

    def _task_metadata(self, *, split: str, selected_count: int) -> dict[str, Any]:
        return {
            "benchmark": self.name,
            "split": split,
            "dataset_path": str(self.dataset_path),
            "case_count": selected_count,
        }

    def _no_samples_error(self, split: str) -> str:
        return f"No Agent-SafetyBench samples loaded for split='{split}' in {self.dataset_path}."
