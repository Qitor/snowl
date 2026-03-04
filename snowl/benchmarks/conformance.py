"""Conformance checks for benchmark adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base import BenchmarkAdapter, validate_benchmark_adapter
from snowl.core import validate_task


@dataclass(frozen=True)
class ConformanceReport:
    ok: bool
    checks: list[dict[str, Any]]


def _sample_schema_ok(sample: dict[str, Any]) -> bool:
    if not isinstance(sample, dict):
        return False
    if sample.get("id") is None:
        return False
    has_io = ("input" in sample) or ("messages" in sample and isinstance(sample.get("messages"), list))
    if not has_io:
        return False
    metadata = sample.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        return False
    return True


def run_conformance(adapter: BenchmarkAdapter) -> ConformanceReport:
    checks: list[dict[str, Any]] = []

    validate_benchmark_adapter(adapter)
    checks.append({"name": "adapter_contract", "ok": True})

    splits = adapter.list_splits()
    checks.append({"name": "list_splits_non_empty", "ok": bool(splits), "value": splits})
    if not splits:
        return ConformanceReport(ok=False, checks=checks)

    split = splits[0]
    tasks_a = adapter.load_tasks(split=split, limit=3)
    tasks_b = adapter.load_tasks(split=split, limit=3)

    ids_a = [t.task_id for t in tasks_a]
    ids_b = [t.task_id for t in tasks_b]
    deterministic = ids_a == ids_b
    checks.append({"name": "deterministic_task_ids", "ok": deterministic, "ids": ids_a})

    schema_ok = True
    for task in tasks_a:
        try:
            validate_task(task)
        except Exception:
            schema_ok = False
            break
    checks.append({"name": "task_schema_valid", "ok": schema_ok, "count": len(tasks_a)})

    sample_ids_a: list[str] = []
    sample_ids_b: list[str] = []
    sample_schema_ok = True
    for ta, tb in zip(tasks_a, tasks_b):
        sa = [dict(s) for s in ta.iter_samples()]
        sb = [dict(s) for s in tb.iter_samples()]
        sample_ids_a.extend([str(x.get("id")) for x in sa])
        sample_ids_b.extend([str(x.get("id")) for x in sb])
        for sample in sa:
            if not _sample_schema_ok(sample):
                sample_schema_ok = False
                break
    checks.append(
        {
            "name": "sample_schema_valid",
            "ok": sample_schema_ok,
            "sample_count": len(sample_ids_a),
        }
    )
    checks.append(
        {
            "name": "deterministic_sample_ids",
            "ok": sample_ids_a == sample_ids_b,
            "sample_ids": sample_ids_a,
        }
    )

    # Benchmark semantic hints (task env + recommended scorer/metrics).
    benchmark_name = getattr(adapter.info, "name", "")
    expected_env = {
        "strongreject": "local",
        "terminalbench": "terminal",
        "osworld": "gui",
    }
    expected_scorer_hint = {
        "strongreject": "benchmarks.strongreject scorer (judge-based)",
        "terminalbench": "benchmarks.terminalbench scorer (unit-test results)",
        "osworld": "benchmarks.osworld scorer (env evaluate score)",
    }
    env_ok = True
    if benchmark_name in expected_env:
        env_ok = all(getattr(t.env_spec, "env_type", None) == expected_env[benchmark_name] for t in tasks_a)
    checks.append(
        {
            "name": "benchmark_semantic_env",
            "ok": env_ok,
            "benchmark": benchmark_name,
            "expected_env_type": expected_env.get(benchmark_name),
            "hint": expected_scorer_hint.get(benchmark_name),
        }
    )

    ok = all(bool(c.get("ok")) for c in checks)
    return ConformanceReport(ok=ok, checks=checks)
