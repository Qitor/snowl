"""Sequential multi-benchmark suite orchestration.

Framework role:
- Parses small suite.yml files and invokes the existing benchmark runner once
  per benchmark, preserving the per-benchmark eval/runtime contracts.

Runtime/usage wiring:
- Used by `snowl suite check` and `snowl suite run`.

Change guardrails:
- Keep this layer orchestration-only. Cross-benchmark scheduling, metric
  normalization, and marketplace/plugin concerns belong in later extensions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from snowl.bench import check_benchmark_conformance, run_benchmark
from snowl.errors import SnowlValidationError
from snowl.project_config import find_project_file, load_project_config


@dataclass(frozen=True)
class SuiteRunResult:
    suite_run_id: str
    status: str
    summary_path: str
    summary: dict[str, Any]


@dataclass(frozen=True)
class _SuiteBenchmark:
    name: str
    adapter: str | None
    adapter_args: dict[str, Any]
    filters: dict[str, Any]
    split: str | None
    limit: int | None


@dataclass(frozen=True)
class _SuiteConfig:
    name: str
    project: Path
    split: str
    limit: int | None
    benchmarks: list[_SuiteBenchmark]
    runtime: dict[str, Any]


def check_suite_config(path: str | Path) -> dict[str, Any]:
    """Validate suite config and benchmark adapter conformance without running trials."""

    suite_path = Path(path).expanduser().resolve()
    config = _load_suite_config(suite_path)
    reports: list[dict[str, Any]] = []
    for benchmark in config.benchmarks:
        try:
            report = check_benchmark_conformance(
                benchmark.name,
                adapter_spec=benchmark.adapter,
                benchmark_args=_dict_to_kv(benchmark.adapter_args),
            )
            reports.append(
                {
                    "name": benchmark.name,
                    "adapter": benchmark.adapter,
                    "ok": bool(report.get("ok")),
                    "checks": report.get("checks", []),
                }
            )
        except Exception as exc:
            reports.append(
                {
                    "name": benchmark.name,
                    "adapter": benchmark.adapter,
                    "ok": False,
                    "error": str(exc),
                }
            )
    return {
        "ok": all(bool(item.get("ok")) for item in reports),
        "suite": config.name,
        "project": str(config.project),
        "benchmarks": reports,
    }


async def run_suite(path: str | Path) -> SuiteRunResult:
    """Run suite benchmarks sequentially and write a suite summary artifact."""

    suite_path = Path(path).expanduser().resolve()
    config = _load_suite_config(suite_path)
    suite_run_id = _new_suite_run_id()
    suite_dir = _suite_output_dir(config.project, suite_run_id)
    suite_dir.mkdir(parents=True, exist_ok=False)

    children: list[dict[str, Any]] = []
    total = 0
    status_counts: dict[str, int] = {
        "success": 0,
        "incorrect": 0,
        "error": 0,
        "limit_exceeded": 0,
        "cancelled": 0,
    }
    failed_runs: list[dict[str, Any]] = []
    runtime = dict(config.runtime)

    for benchmark in config.benchmarks:
        child: dict[str, Any] = {
            "name": benchmark.name,
            "adapter": benchmark.adapter,
            "split": benchmark.split or config.split,
            "limit": benchmark.limit if benchmark.limit is not None else config.limit,
            "adapter_args": dict(benchmark.adapter_args),
            "filters": dict(benchmark.filters),
        }
        try:
            result = await run_benchmark(
                benchmark.name,
                project_path=config.project,
                split=child["split"],
                limit=child["limit"],
                adapter_spec=benchmark.adapter,
                benchmark_args=_dict_to_kv(benchmark.adapter_args),
                benchmark_filters=_dict_to_kv(benchmark.filters),
                max_running_trials=_optional_int(runtime.get("max_running_trials")),
                max_container_slots=_optional_int(runtime.get("max_container_slots")),
                max_builds=_optional_int(runtime.get("max_builds")),
                max_scoring_tasks=_optional_int(runtime.get("max_scoring_tasks")),
                provider_budgets=_provider_budgets(runtime.get("provider_budgets")),
                experiment_id=suite_run_id,
            )
            child.update(_child_run_summary(result.artifacts_dir))
            child["status"] = "completed" if result.summary.error == 0 else "completed_with_errors"
            child["summary"] = {
                "total": result.summary.total,
                "success": result.summary.success,
                "incorrect": result.summary.incorrect,
                "error": result.summary.error,
                "limit_exceeded": result.summary.limit_exceeded,
                "cancelled": result.summary.cancelled,
            }
            total += result.summary.total
            status_counts["success"] += result.summary.success
            status_counts["incorrect"] += result.summary.incorrect
            status_counts["error"] += result.summary.error
            status_counts["limit_exceeded"] += result.summary.limit_exceeded
            status_counts["cancelled"] += result.summary.cancelled
            if result.summary.error:
                failed_runs.append(
                    {
                        "name": benchmark.name,
                        "run_id": child.get("run_id"),
                        "artifacts_dir": child.get("artifacts_dir"),
                        "error": f"{result.summary.error} trial(s) ended with error",
                    }
                )
        except Exception as exc:
            child["status"] = "failed"
            child["error"] = str(exc)
            failed_runs.append({"name": benchmark.name, "adapter": benchmark.adapter, "error": str(exc)})
        children.append(child)

    status = "failed" if failed_runs else "completed"
    summary = {
        "schema_version": "v1",
        "suite_run_id": suite_run_id,
        "suite_name": config.name,
        "project": str(config.project),
        "status": status,
        "benchmarks": children,
        "total": total,
        "status_counts": status_counts,
        "failed_runs": failed_runs,
    }
    summary_path = suite_dir / "suite_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return SuiteRunResult(
        suite_run_id=suite_run_id,
        status=status,
        summary_path=str(summary_path),
        summary=summary,
    )


def _load_suite_config(path: Path) -> _SuiteConfig:
    if not path.exists():
        raise SnowlValidationError(f"Suite config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise SnowlValidationError("suite.yml must contain a mapping.")
    suite = raw.get("suite")
    if not isinstance(suite, dict):
        raise SnowlValidationError("suite.yml must contain a 'suite' mapping.")

    name = str(suite.get("name") or "").strip()
    if not name:
        raise SnowlValidationError("suite.name is required.")
    project_raw = suite.get("project") or "project.yml"
    project = _resolve_path(path.parent, project_raw)
    split = str(suite.get("split") or "test")
    limit = _optional_int(suite.get("limit"))
    benchmarks_raw = suite.get("benchmarks")
    if not isinstance(benchmarks_raw, list) or not benchmarks_raw:
        raise SnowlValidationError("suite.benchmarks must be a non-empty list.")

    benchmarks: list[_SuiteBenchmark] = []
    for idx, item in enumerate(benchmarks_raw, start=1):
        if not isinstance(item, dict):
            raise SnowlValidationError(f"suite.benchmarks[{idx}] must be a mapping.")
        bench_name = str(item.get("name") or "").strip()
        if not bench_name:
            raise SnowlValidationError(f"suite.benchmarks[{idx}].name is required.")
        adapter = item.get("adapter")
        adapter_spec = _resolve_adapter_spec(path.parent, adapter) if adapter else None
        adapter_args = _resolve_arg_mapping(path.parent, item.get("adapter_args") or {})
        filters = {str(k): v for k, v in dict(item.get("filters") or {}).items()}
        benchmarks.append(
            _SuiteBenchmark(
                name=bench_name,
                adapter=adapter_spec,
                adapter_args=adapter_args,
                filters=filters,
                split=str(item["split"]) if item.get("split") is not None else None,
                limit=_optional_int(item.get("limit")),
            )
        )

    runtime = raw.get("runtime") or {}
    if not isinstance(runtime, dict):
        raise SnowlValidationError("runtime must be a mapping when provided.")

    return _SuiteConfig(
        name=name,
        project=project,
        split=split,
        limit=limit,
        benchmarks=benchmarks,
        runtime=dict(runtime),
    )


def _suite_output_dir(project: Path, suite_run_id: str) -> Path:
    project_file = find_project_file(project)
    if project_file is not None:
        try:
            root = load_project_config(project_file).root_dir
        except Exception:
            root = project_file.parent
    else:
        root = project if project.is_dir() else project.parent
    return root / ".snowl" / "suites" / suite_run_id


def _new_suite_run_id() -> str:
    return "suite-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _resolve_path(base: Path, value: object) -> Path:
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _resolve_adapter_spec(base: Path, value: object) -> str:
    raw = str(value or "").strip()
    if ":" not in raw:
        return raw
    module_raw, object_name = raw.rsplit(":", 1)
    module = Path(module_raw).expanduser()
    if not module.is_absolute():
        module = (base / module).resolve()
    return f"{module}:{object_name.strip()}"


def _resolve_arg_mapping(base: Path, mapping: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        key_str = str(key)
        if isinstance(value, str) and _looks_like_relative_path_key(key_str, value):
            out[key_str] = str(_resolve_path(base, value))
        else:
            out[key_str] = value
    return out


def _looks_like_relative_path_key(key: str, value: str) -> bool:
    if Path(value).expanduser().is_absolute():
        return False
    return key.endswith(("_path", "_dir", "_root")) or value.startswith(("./", "../"))


def _dict_to_kv(mapping: dict[str, Any]) -> list[str] | None:
    if not mapping:
        return None
    return [f"{key}={value}" for key, value in mapping.items()]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _provider_budgets(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SnowlValidationError("runtime.provider_budgets must be a mapping.")
    return {str(key): int(val) for key, val in value.items()}


def _child_run_summary(artifacts_dir: str) -> dict[str, Any]:
    out: dict[str, Any] = {"artifacts_dir": str(artifacts_dir)}
    run_dir = Path(artifacts_dir)
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            out["run_id"] = manifest.get("run_id") or run_dir.name
            out["experiment_id"] = manifest.get("experiment_id")
        except Exception:
            out["run_id"] = run_dir.name
    else:
        out["run_id"] = run_dir.name
    primary = _read_primary_metrics(run_dir / "benchmark_summary.json")
    if primary:
        out["primary_metrics"] = primary
    return out


def _read_primary_metrics(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    metrics: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metric = row.get("primary_metric") or row.get("metric")
        value = row.get("primary_metric_value")
        if value is None and isinstance(row.get("metric_means"), dict) and metric:
            value = row["metric_means"].get(metric)
        if value is None and isinstance(row.get("metrics"), dict) and metric:
            value = row["metrics"].get(metric)
        if metric is not None or value is not None:
            metrics.append(
                {
                    "benchmark": row.get("benchmark"),
                    "agent_id": row.get("agent_id"),
                    "variant_id": row.get("variant_id"),
                    "metric": metric,
                    "value": value,
                }
            )
    return metrics
