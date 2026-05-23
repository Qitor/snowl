"""Coding-agent prompt-injection benchmark adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import read_json_array, stable_benchmark_id
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


@dataclass(frozen=True)
class IPICodingAgentBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = ""
    rows: list[dict[str, Any]] | None = None
    vector: str | None = None
    severity: str | None = None
    benign: bool | str | None = None
    injected: bool | str | None = None
    name: str = "ipi_coding_agent"
    description: str = "Coding-agent prompt-injection benchmark adapter."
    default_split: str = "test"
    stringify_filter_values: bool = False

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name="IPI Coding Agent",
            short_description="Prompt-injection resistance for coding agents",
            domain="agentic_safety",
            benchmark_type="safety",
            family="ipi_coding_agent",
            primary_metric="ipi_coding_agent_score",
            higher_is_better=True,
            sample_preview_mode="code_trace",
            dashboard_tags=["prompt_injection", "coding", "tool_use"],
        )

    def _iter_rows(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return [dict(row) for row in self.rows]
        if not self.dataset_path:
            raise SnowlValidationError("IPI coding-agent benchmark requires rows=... or dataset_path=....")
        data = read_json_array(self.dataset_path, not_found_message="IPI coding-agent dataset not found", invalid_message="IPI coding-agent dataset must be a JSON array")
        return [dict(row) for row in data if isinstance(row, dict)]

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get("split") or self.default_split)

    def _matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        if self.vector and str(row.get("injection_vector") or "") != str(self.vector):
            return False
        if self.severity and str(row.get("severity") or "") != str(self.severity):
            return False
        benign_value = _coerce_bool(self.benign)
        if benign_value is not None and bool(row.get("is_benign")) != benign_value:
            return False
        injected_value = _coerce_bool(self.injected)
        if injected_value is not None and (not bool(row.get("is_benign"))) != injected_value:
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
        task_description = str(row.get("task_description") or "").strip()
        issue_text = str(row.get("issue_text") or "").strip()
        if not task_description:
            return None
        sample_id = str(row.get("id") or "").strip() or stable_benchmark_id("ipi-coding-agent", row_index, task_description)
        prompt = task_description
        if issue_text:
            prompt += "\n\nIssue context:\n" + issue_text
        repo_files = dict(row.get("repo_files") or {})
        compose_file = str(row.get("compose_file") or "").strip()
        docker_image = str(row.get("docker_image") or row.get("image") or "").strip()
        provider_name = "docker_container" if docker_image else "compose_terminal"
        requires_container = bool(compose_file or docker_image)
        check_command = row.get("check_command") or row.get("verification_command")
        runtime_startup: dict[str, Any] = {
            "network": "disabled",
            "repo_files": repo_files,
            "verification_command": check_command,
        }
        if compose_file:
            runtime_startup["compose_file"] = compose_file
        if docker_image:
            runtime_startup["image"] = docker_image
        metadata = {
            "split": row_split,
            "task_description": task_description,
            "issue_text": issue_text,
            "injection_vector": row.get("injection_vector"),
            "payload_category": row.get("payload_category"),
            "payload_sophistication": row.get("payload_sophistication"),
            "severity": row.get("severity"),
            "payload_indicator": row.get("payload_indicator"),
            "expected_malicious_action": row.get("expected_malicious_action"),
            "is_benign": bool(row.get("is_benign")),
            "repo_files": repo_files,
            "workspace_before": repo_files,
            "verification_command": check_command,
            "check_command": check_command,
            "expected_fix": row.get("expected_fix"),
            "forbidden_paths": list(row.get("persistence_targets") or []),
            "workspace": {
                "enabled": True,
                "repo_files": repo_files,
                "artifacts": list(row.get("artifacts") or []),
            },
            "runtime_container": {
                "benchmark": self.name,
                "provider_name": provider_name,
                "requires_container": requires_container,
                "network": "disabled",
                "check_command": str(check_command) if check_command else None,
                "workspace": {
                    "enabled": True,
                    "repo_files": repo_files,
                    "artifacts": list(row.get("artifacts") or []),
                },
                "startup": runtime_startup,
            },
        }
        return {"id": sample_id, "input": prompt, "metadata": metadata}

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="terminal", provided_ops=("process.run", "terminal.exec", "terminal.capture", "terminal.wait"))


def _coerce_bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return None
