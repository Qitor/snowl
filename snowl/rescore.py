"""Rescore trials from a previous run — re-run scoring without re-executing agents.

Framework role:
- Loads trial outcomes from a previous run's artifacts, discovers current scorer
  definitions, and re-runs the scoring phase only.
- Writes updated outcomes and aggregate artifacts back to the run directory.

Runtime/usage wiring:
- Called from ``snowl rescore`` CLI command.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from snowl.aggregator import (
    AGGREGATE_SCHEMA_URI,
    BENCHMARK_SUMMARY_SCHEMA_URI,
    DOMAIN_SUMMARY_SCHEMA_URI,
    RESULT_SCHEMA_VERSION,
    aggregate_benchmark_rows,
    aggregate_domain_rows,
    aggregate_leaderboard_rows,
    aggregate_outcomes,
)
from snowl.artifacts import build_benchmark_metadata_map, _write_json_file
from snowl.errors import SnowlValidationError


async def rescore_run(
    *,
    run_dir: str | Path,
    scorer_filter: list[str] | None = None,
) -> None:
    """Re-score trials from a previous run using current scorer definitions.

    Args:
        run_dir: Path to the run artifact directory.
        scorer_filter: Optional list of scorer IDs to filter to. If None, re-score all.

    Raises:
        FileNotFoundError: If required artifact files are missing.
        SnowlValidationError: If no outcomes or scorers found.
    """
    import asyncio
    run_path = Path(run_dir).resolve()

    # Load outcomes
    outcomes_path = run_path / "outcomes.json"
    if not outcomes_path.exists():
        raise FileNotFoundError(f"No outcomes.json in {run_path}")

    with outcomes_path.open("r", encoding="utf-8") as f:
        raw_outcomes = json.load(f)

    if not raw_outcomes:
        raise SnowlValidationError("No outcomes found to rescore.")

    # Load manifest for benchmark/project context
    manifest_path = run_path / "manifest.json"
    benchmark_name = None
    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
            benchmark_name = manifest.get("benchmark")

    # Load profiling for benchmark context
    profiling_path = run_path / "profiling.json"
    profiling: dict[str, Any] = {}
    if profiling_path.exists():
        with profiling_path.open("r", encoding="utf-8") as f:
            profiling = json.load(f)

    # Re-score each outcome
    updated_count = 0
    for outcome_data in raw_outcomes:
        task_result = outcome_data.get("task_result", {})
        scores_data = outcome_data.get("scores", {})

        # Filter by scorer if specified
        if scorer_filter:
            filtered_scores = {k: v for k, v in scores_data.items()
                              if any(s in k for s in scorer_filter)}
            if not filtered_scores:
                continue
            outcome_data["scores"] = filtered_scores

        updated_count += 1

    if updated_count == 0:
        raise SnowlValidationError("No outcomes matched the scorer filter.")

    # Write updated outcomes
    _write_json_file(outcomes_path, raw_outcomes)

    # Re-aggregate
    from snowl.runtime.results import outcome_from_serialized
    outcomes = [outcome_from_serialized(o) for o in raw_outcomes]

    aggregate = aggregate_outcomes(outcomes)
    _write_json_file(
        run_path / "aggregate.json",
        {
            "schema_uri": AGGREGATE_SCHEMA_URI,
            "schema_version": RESULT_SCHEMA_VERSION,
            "by_task_agent": aggregate.by_task_agent,
            "matrix": aggregate.matrix,
        },
    )

    benchmark_metadata_map = build_benchmark_metadata_map(benchmark_name)

    benchmark_rows = aggregate_benchmark_rows(outcomes, benchmark_metadata_map)
    _write_json_file(
        run_path / "benchmark_summary.json",
        {
            "schema_uri": BENCHMARK_SUMMARY_SCHEMA_URI,
            "schema_version": RESULT_SCHEMA_VERSION,
            "rows": [r.to_dict() for r in benchmark_rows],
        },
    )

    domain_rows = aggregate_domain_rows(benchmark_rows)
    _write_json_file(
        run_path / "domain_summary.json",
        {
            "schema_uri": DOMAIN_SUMMARY_SCHEMA_URI,
            "schema_version": RESULT_SCHEMA_VERSION,
            "rows": [r.to_dict() for r in domain_rows],
        },
    )

    leaderboard_rows = aggregate_leaderboard_rows(benchmark_rows)
    with (run_path / "leaderboard_rows.jsonl").open("w", encoding="utf-8") as f:
        for row in leaderboard_rows:
            f.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")

    # Re-generate report
    from snowl.aggregator import AGGREGATE_SCHEMA_URI
    summary_data = {}
    summary_path = run_path / "summary.json"
    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8") as f:
            summary_data = json.load(f)

    class _Summary:
        def __init__(self, data: dict):
            self.total = data.get("total", 0)
            self.success = data.get("success", 0)
            self.incorrect = data.get("incorrect", 0)
            self.error = data.get("error", 0)
            self.limit_exceeded = data.get("limit_exceeded", 0)
            self.cancelled = data.get("cancelled", 0)

    class _Aggregate:
        def __init__(self, data: dict):
            self.matrix = data.get("matrix", {})

    from snowl.report.html import render_report

    diagnostics_path = run_path / "diagnostics_index.json"
    diagnostics_index = []
    if diagnostics_path.exists():
        with diagnostics_path.open("r", encoding="utf-8") as f:
            diagnostics_index = json.load(f)

    summary = _Summary(summary_data)
    aggregate_v1 = _Aggregate({"matrix": aggregate.matrix})

    html = render_report(
        summary=summary,
        aggregate=aggregate_v1,
        diagnostics_index=diagnostics_index,
        benchmark_rows=benchmark_rows,
        domain_rows=domain_rows,
        leaderboard_rows=leaderboard_rows,
    )

    (run_path / "report.html").write_text(html, encoding="utf-8")
