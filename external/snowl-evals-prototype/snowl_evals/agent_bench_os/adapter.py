"""AgentBench OS adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import read_json_array, stable_benchmark_id
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


@dataclass(frozen=True)
class AgentBenchOSBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = ""
    test_dataset_path: str = ""
    rows: list[dict[str, Any]] | None = None
    name: str = "agent_bench_os"
    description: str = "AgentBench OS benchmark adapter."
    default_split: str = "dev"

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name="AgentBench OS",
            short_description="Operating-system agent tasks",
            domain="agentic_capability",
            benchmark_type="capability",
            family="agent_bench",
            primary_metric="agent_bench_os_success",
            higher_is_better=True,
            sample_preview_mode="code_trace",
            dashboard_tags=["terminal", "tool_use", "os"],
        )

    def _iter_rows(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return [dict(row) for row in self.rows]
        paths = {"dev": self.dataset_path, "test": self.test_dataset_path or self.dataset_path}
        out: list[dict[str, Any]] = []
        for split, path in paths.items():
            if not path:
                continue
            for row in read_json_array(path, not_found_message="AgentBench OS dataset not found", invalid_message="AgentBench OS dataset must be a JSON array"):
                if isinstance(row, dict):
                    out.append({**row, "split": split})
        if not out:
            raise SnowlValidationError("AgentBench OS requires rows=... or dataset_path=....")
        return out

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get("split") or self.default_split)

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = selected_count
        prompt = str(row.get("description") or row.get("input") or "").strip()
        if not prompt:
            return None
        evaluation = dict(row.get("evaluation") or {})
        target = evaluation.get("match")
        sample_id = str(row.get("id") or "").strip() or stable_benchmark_id("agent-bench-os", row_index, prompt)
        metadata: dict[str, Any] = {
            "split": row_split,
            "labels": list(row.get("labels") or []),
            "create": row.get("create"),
            "start": row.get("start"),
            "evaluation": evaluation,
            "answer": target,
            "target": target,
            "scoring": "match" if target is not None else "command_check",
        }
        startup = _runtime_startup(row)
        if startup:
            check_command = startup.get("check_command")
            if check_command:
                metadata["check_command"] = check_command
                metadata["verification_command"] = check_command
            metadata["runtime_container"] = {
                "benchmark": self.name,
                "provider_name": startup.pop("provider_name", "compose_terminal"),
                "requires_container": True,
                "init_command": startup.get("init_command"),
                "start_command": startup.get("start_command"),
                "check_command": check_command,
                "network": startup.get("network"),
                "workspace": dict(startup.get("workspace") or {}),
                "startup": startup,
            }
        return {"id": f"agent-bench-os-{sample_id}", "input": prompt, "metadata": metadata}

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="terminal", provided_ops=("process.run", "terminal.exec", "terminal.capture", "terminal.wait"))


def _runtime_startup(row: Mapping[str, Any]) -> dict[str, Any]:
    create = row.get("create")
    if not isinstance(create, Mapping):
        return {}
    startup: dict[str, Any] = {}
    init = create.get("init")
    if isinstance(init, Mapping):
        if init.get("code") is not None:
            startup["init_command"] = str(init.get("code"))
        if init.get("file") is not None:
            startup["init_file"] = str(init.get("file"))
    elif isinstance(init, str):
        startup["init_command"] = init
    if row.get("start"):
        startup["start_command"] = str(row.get("start"))
    evaluation = row.get("evaluation")
    if isinstance(evaluation, Mapping):
        command = evaluation.get("command") or evaluation.get("check_command") or evaluation.get("verification_command")
        if command is not None:
            startup["check_command"] = str(command)
    if create.get("compose_file"):
        startup["compose_file"] = str(create.get("compose_file"))
    if create.get("docker_image") or create.get("image"):
        startup["provider_name"] = "docker_container"
        startup["image"] = str(create.get("docker_image") or create.get("image"))
    if create.get("network"):
        startup["network"] = str(create.get("network"))
    repo_files = create.get("repo_files")
    if isinstance(repo_files, Mapping):
        startup["workspace"] = {"enabled": True, "repo_files": dict(repo_files)}
    return startup
