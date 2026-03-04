from __future__ import annotations

import asyncio
import json
from pathlib import Path

from snowl.bench import check_benchmark_conformance, list_benchmarks
from snowl.cli import main


def _write_project(tmp: Path) -> None:
    (tmp / "agent.py").write_text(
        """
from snowl.core import StopReason

class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        state.output = {"message": {"role": "assistant", "content": "ok"}, "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2}, "trace_events": []}
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
        {"id": "1", "split": "test", "input": "x", "target": "y"},
        {"id": "2", "split": "train", "input": "x2", "target": "y2"},
    ]
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_bench_list_contains_jsonl() -> None:
    names = {item["name"] for item in list_benchmarks()}
    assert "jsonl" in names


def test_bench_check_and_run_jsonl(tmp_path: Path) -> None:
    _write_project(tmp_path)
    dataset = tmp_path / "bench.jsonl"
    _write_jsonl(dataset)

    report = check_benchmark_conformance("jsonl", benchmark_args=[f"dataset_path={dataset}"])
    assert report["ok"] is True

    rc = main(
        [
            "bench",
            "run",
            "jsonl",
            "--project",
            str(tmp_path),
            "--split",
            "test",
            "--adapter-arg",
            f"dataset_path={dataset}",
            "--no-ui",
        ]
    )
    assert rc == 0


def test_bench_list_cli(tmp_path: Path) -> None:
    rc = main(["bench", "list"])
    assert rc == 0


def test_bench_run_keyboard_interrupt_prints_log_path(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_project(tmp_path)
    runs = tmp_path / ".snowl" / "runs" / "run-20260303T110500Z"
    runs.mkdir(parents=True)
    (runs / "run.log").write_text("partial\n", encoding="utf-8")

    def _raise_interrupt(coro):
        coro.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(asyncio, "run", _raise_interrupt)
    rc = main(["bench", "run", "jsonl", "--project", str(tmp_path), "--no-ui"])
    out = capsys.readouterr().out
    assert rc == 130
    assert "Interrupted by user." in out
    assert f"log={runs / 'run.log'}" in out
