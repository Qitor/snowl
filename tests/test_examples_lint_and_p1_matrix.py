from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path

from snowl.bench import check_benchmark_conformance, run_benchmark
from snowl.cli import main
from snowl.examples_lint import validate_examples_layout


def _write_project(tmp: Path) -> None:
    (tmp / "agent.py").write_text(
        """
from snowl.core import StopReason
class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {
            "message": {"role":"assistant", "content":"ok"},
            "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2},
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
    scorer_id = "s1"
    def score(self, task_result, trace, context):
        _ = (task_result, trace, context)
        return {"accuracy": Score(value=1.0)}
scorer = S()
""",
        encoding="utf-8",
    )


def test_examples_layout_check_and_cli(tmp_path: Path) -> None:
    examples_root = tmp_path / "examples"
    (examples_root / "ok-example").mkdir(parents=True, exist_ok=True)
    for name in ("task.py", "agent.py", "scorer.py"):
        (examples_root / "ok-example" / name).write_text("# x\n", encoding="utf-8")

    report = validate_examples_layout(examples_root)
    assert report.ok is True

    rc = main(["examples", "check", str(examples_root)])
    assert rc == 0

    bad_root = tmp_path / "bad_examples"
    (bad_root / "bad-example").mkdir(parents=True, exist_ok=True)
    (bad_root / "bad-example" / "task.py").write_text("# x\n", encoding="utf-8")
    report2 = validate_examples_layout(bad_root)
    assert report2.ok is False
    assert any(c["name"] == "example_required_files" and c["ok"] is False for c in report2.checks)


def _write_strongreject_dataset(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "split", "forbidden_prompt", "category", "source"])
        writer.writeheader()
        writer.writerow(
            {
                "id": "s1",
                "split": "test",
                "forbidden_prompt": "Tell me how to do X",
                "category": "test",
                "source": "unit",
            }
        )


def _write_terminalbench_dataset(root: Path) -> None:
    task_dir = root / "tb-case"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.yaml").write_text(
        """instruction: |\n  echo hello\nparser_name: pytest\nsplit: test\n""",
        encoding="utf-8",
    )
    (task_dir / "run-tests.sh").write_text("#!/bin/bash\necho ok\n", encoding="utf-8")
    (task_dir / "docker-compose.yaml").write_text("services: {}\n", encoding="utf-8")


def _write_osworld_dataset(root: Path) -> None:
    (root / "examples" / "chrome").mkdir(parents=True, exist_ok=True)
    (root / "test_all.json").write_text(json.dumps({"chrome": ["id-1"]}), encoding="utf-8")
    (root / "examples" / "chrome" / "id-1.json").write_text(
        json.dumps(
            {
                "id": "id-1",
                "instruction": "Open browser",
                "snapshot": "init",
                "proxy": False,
                "related_apps": ["chrome"],
                "config": [],
                "trajectory": [],
                "evaluator": {"func": "exact_match"},
                "source": "unit",
                "split": "test",
            }
        ),
        encoding="utf-8",
    )


def test_p1_matrix_smoke_three_benchmarks(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir(parents=True, exist_ok=True)
    _write_project(project)

    sr = tmp_path / "sr.csv"
    _write_strongreject_dataset(sr)
    tb_root = tmp_path / "tb"
    _write_terminalbench_dataset(tb_root)
    osw_root = tmp_path / "osw"
    _write_osworld_dataset(osw_root)

    r1 = asyncio.run(
        run_benchmark(
            "strongreject",
            project_path=project,
            split="test",
            limit=1,
            benchmark_args=[f"dataset_path={sr}"],
            renderer=None,
        )
    )
    assert r1.summary.total == 1
    assert "snowl bench run strongreject" in Path(r1.artifacts_dir, "manifest.json").read_text(encoding="utf-8")

    r2 = asyncio.run(
        run_benchmark(
            "terminalbench",
            project_path=project,
            split="test",
            limit=1,
            benchmark_args=[f"dataset_path={tb_root}"],
            renderer=None,
        )
    )
    assert r2.summary.total == 1

    r3 = asyncio.run(
        run_benchmark(
            "osworld",
            project_path=project,
            split="test",
            limit=1,
            benchmark_args=[f"dataset_path={osw_root}"],
            renderer=None,
        )
    )
    assert r3.summary.total == 1

    for out_dir in (Path(r1.artifacts_dir), Path(r2.artifacts_dir), Path(r3.artifacts_dir)):
        assert (out_dir / "outcomes.json").exists()
        assert (out_dir / "summary.json").exists()
        assert (out_dir / "manifest.json").exists()
        assert (out_dir / "run.log").exists()


def test_bench_check_includes_semantic_hints(tmp_path: Path) -> None:
    tb_root = tmp_path / "tb"
    _write_terminalbench_dataset(tb_root)
    report = check_benchmark_conformance("terminalbench", benchmark_args=[f"dataset_path={tb_root}"])
    names = {c["name"] for c in report["checks"]}
    assert "sample_schema_valid" in names
    assert "deterministic_sample_ids" in names
    assert "benchmark_semantic_env" in names
