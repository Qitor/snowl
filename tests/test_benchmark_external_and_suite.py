from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml

from snowl.benchmarks.external import load_external_adapter
from snowl.cli import main
from snowl.errors import SnowlValidationError
from snowl.suite import check_suite_config, run_suite


def _write_project(tmp: Path) -> None:
    (tmp / "agent.py").write_text(
        """
from snowl.core import StopReason

class A:
    agent_id = "a1"

    async def run(self, state, context, tools=None):
        state.output = {
            "message": {"role": "assistant", "content": "hello ok"},
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state

agent = A()
""",
        encoding="utf-8",
    )
    (tmp / "scorer.py").write_text(
        """
from snowl.core import Score

class S:
    scorer_id = "s"

    def score(self, task_result, trace, context):
        return {"accuracy": Score(value=1.0)}

scorer = S()
""",
        encoding="utf-8",
    )


def _write_jsonl(path: Path) -> None:
    rows = [
        {"id": "1", "split": "test", "input": "say ok", "target": "ok"},
        {"id": "2", "split": "dev", "input": "say dev", "target": "dev"},
    ]
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_bench_scaffold_check_and_run_external_adapter(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_project(project)
    scaffold = tmp_path / "mybench"

    rc = main(["bench", "scaffold", "mybench", "--out", str(scaffold)])
    assert rc == 0
    assert (scaffold / "adapter.py").exists()
    assert (scaffold / "data.jsonl").exists()

    adapter_spec = f"{scaffold / 'adapter.py'}:adapter"
    dataset_arg = f"dataset_path={scaffold / 'data.jsonl'}"
    rc = main(["bench", "check", "mybench", "--adapter", adapter_spec, "--adapter-arg", dataset_arg])
    assert rc == 0

    rc = main(
        [
            "bench",
            "run",
            "mybench",
            "--adapter",
            adapter_spec,
            "--adapter-arg",
            dataset_arg,
            "--project",
            str(project),
            "--split",
            "test",
            "--limit",
            "1",
            "--no-ui",
            "--no-web-monitor",
        ]
    )
    assert rc == 0
    run_dirs = sorted([p for p in (project / ".snowl" / "runs").iterdir() if p.is_dir() and p.name != "by_run_id"])
    assert run_dirs
    manifest = json.loads((run_dirs[-1] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["benchmark"] == "mybench"


def test_external_adapter_loader_supports_instance_factory_and_class(tmp_path: Path) -> None:
    dataset = tmp_path / "data.jsonl"
    _write_jsonl(dataset)
    module = tmp_path / "adapter_variants.py"
    module.write_text(
        f'''
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import read_jsonl_rows


@dataclass(frozen=True)
class TinyAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = r"{dataset}"
    name: str = "tiny"
    description: str = "Tiny adapter"

    def benchmark_info(self):
        return BenchmarkInfo(name=self.name, description=self.description)

    def _iter_rows(self):
        return read_jsonl_rows(self.dataset_path, not_found_message="missing")

    def _row_split(self, row, *, row_index):
        return row.get("split", "test")

    def _row_to_sample(self, row, *, row_index, row_split, selected_count):
        return {{"id": row.get("id"), "input": row.get("input"), "metadata": row}}


instance_adapter = TinyAdapter()


def factory_adapter(**kwargs):
    return TinyAdapter(**kwargs)
''',
        encoding="utf-8",
    )

    assert load_external_adapter(f"{module}:instance_adapter").info.name == "tiny"
    assert load_external_adapter(f"{module}:factory_adapter", dataset_path=str(dataset)).info.name == "tiny"
    assert load_external_adapter(f"{module}:TinyAdapter", dataset_path=str(dataset)).info.name == "tiny"


def test_invalid_external_adapter_spec_is_actionable(tmp_path: Path) -> None:
    try:
        load_external_adapter(str(tmp_path / "missing.py"))
    except SnowlValidationError as exc:
        assert "module.py:object" in str(exc)
    else:
        raise AssertionError("expected invalid adapter spec to fail")


def test_suite_check_and_run_writes_summary(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_project(project)
    builtin_dataset = tmp_path / "bench.jsonl"
    _write_jsonl(builtin_dataset)

    scaffold = tmp_path / "mybench"
    assert main(["bench", "scaffold", "mybench", "--out", str(scaffold)]) == 0

    suite_path = tmp_path / "suite.yml"
    suite_path.write_text(
        yaml.safe_dump(
            {
                "suite": {
                    "name": "safety-smoke",
                    "project": "./project",
                    "split": "test",
                    "limit": 1,
                    "benchmarks": [
                        {"name": "jsonl", "adapter_args": {"dataset_path": "./bench.jsonl"}},
                        {
                            "name": "mybench",
                            "adapter": "./mybench/adapter.py:adapter",
                            "adapter_args": {"dataset_path": "./mybench/data.jsonl"},
                        },
                    ],
                },
                "runtime": {
                    "max_running_trials": 2,
                    "max_scoring_tasks": 2,
                    "provider_budgets": {"default": 2},
                },
            }
        ),
        encoding="utf-8",
    )

    check = check_suite_config(suite_path)
    assert check["ok"] is True
    assert [item["name"] for item in check["benchmarks"]] == ["jsonl", "mybench"]

    result = asyncio.run(run_suite(suite_path))
    assert result.status == "completed"
    summary_path = Path(result.summary_path)
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["suite_name"] == "safety-smoke"
    assert summary["total"] == 2
    assert summary["status_counts"]["success"] == 2
    assert len(summary["benchmarks"]) == 2
    assert all(item.get("run_id") for item in summary["benchmarks"])


def test_suite_cli_check(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_project(project)
    dataset = tmp_path / "bench.jsonl"
    _write_jsonl(dataset)
    suite_path = tmp_path / "suite.yml"
    suite_path.write_text(
        yaml.safe_dump(
            {
                "suite": {
                    "name": "cli-suite",
                    "project": "./project",
                    "benchmarks": [
                        {"name": "jsonl", "adapter_args": {"dataset_path": "./bench.jsonl"}},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    assert main(["suite", "check", str(suite_path)]) == 0
