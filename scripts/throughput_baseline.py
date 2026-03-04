#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter
from snowl.benchmarks.terminalbench import TerminalBenchBenchmarkAdapter


def _measure_adapter(adapter: Any, split: str, limit: int) -> dict[str, Any]:
    started = time.time()
    tasks = adapter.load_tasks(split=split, limit=limit)
    elapsed = time.time() - started
    sample_count = 0
    for task in tasks:
        sample_count += len(list(task.iter_samples()))
    return {
        "task_count": len(tasks),
        "sample_count": sample_count,
        "load_duration_ms": int(elapsed * 1000),
        "samples_per_sec": (sample_count / elapsed) if elapsed > 0 else 0.0,
    }


def run_baseline(root: Path, split: str, limit: int) -> dict[str, Any]:
    started = time.time()
    terminal = TerminalBenchBenchmarkAdapter(
        dataset_path=str(root / "references" / "terminal-bench" / "original-tasks")
    )
    osworld = OSWorldBenchmarkAdapter(
        dataset_path=str(root / "references" / "OSWorld" / "evaluation_examples")
    )
    report = {
        "timestamp": int(time.time()),
        "split": split,
        "limit": limit,
        "terminalbench": _measure_adapter(terminal, split=split, limit=limit),
        "osworld": _measure_adapter(osworld, split=split, limit=limit),
    }
    report["total_duration_ms"] = int((time.time() - started) * 1000)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Snowl benchmark throughput baseline")
    parser.add_argument("--root", default=".", help="project root path")
    parser.add_argument("--split", default="test")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out", default=".snowl/profiles/throughput_baseline.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report = run_baseline(root=root, split=args.split, limit=args.limit)
    out_path = (root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

