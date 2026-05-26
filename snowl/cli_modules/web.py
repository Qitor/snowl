"""Web monitor, report, compare, rescore, and export command implementations."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from snowl.web.runtime import WebRuntimeError, ensure_next_build, ensure_next_runtime


def _cmd_web_monitor(
    *,
    project: str,
    host: str,
    port: int,
    poll_interval_sec: float,
) -> int:
    env = dict(os.environ)
    resolved_project = str(Path(project).resolve())
    env["SNOWL_PROJECT_DIR"] = resolved_project
    env["SNOWL_POLL_INTERVAL_SEC"] = str(float(poll_interval_sec))
    dev_mode = os.getenv("SNOWL_WEB_DEV", "0").lower() in {"1", "true", "on", "yes"}
    cmd = [
        "npm",
        "run",
        ("dev" if dev_mode else "start"),
        "--",
        "--hostname",
        str(host),
        "--port",
        str(int(port)),
    ]
    try:
        print("[web] ensure deps")
        runtime = ensure_next_runtime(log=print)
        env["SNOWL_WEB_CACHE_KEY"] = runtime.cache_key
        env["SNOWL_WEB_SOURCE_DIR"] = str(runtime.source_dir)
        env["SNOWL_WEB_SOURCE_MODE"] = runtime.source_mode
        monitor_cfg_path = runtime.app_dir / ".snowl-monitor.json"
        monitor_cfg_path.write_text(
            json.dumps(
                {
                    "project_dir": resolved_project,
                    "poll_interval_sec": float(poll_interval_sec),
                    "cache_key": runtime.cache_key,
                    "source_dir": str(runtime.source_dir),
                    "source_mode": runtime.source_mode,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if dev_mode:
            print("[web] ensure build: skipped (SNOWL_WEB_DEV=1)")
        else:
            print("[web] ensure build")
            ensure_next_build(runtime, log=print)
        print("[web] start server")
        print(f"Web monitor: http://{host}:{int(port)}")
        completed = subprocess.run(
            cmd,
            cwd=str(runtime.app_dir),
            env=env,
            check=False,
        )
        return int(completed.returncode)
    except KeyboardInterrupt:
        return 130
    except WebRuntimeError as exc:
        print(f"Web monitor bootstrap failed: {exc}")
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"Web monitor bootstrap failed: command exited with status {exc.returncode}: {' '.join(exc.cmd)}")
        return 2


def _resolve_run_dir(run_id: str, project: str) -> Path:
    """Resolve a run_id to its artifact directory."""
    base_dir = Path(project).resolve()
    runs_root = base_dir / ".snowl" / "runs"

    if run_id == "latest":
        candidates = [d for d in runs_root.iterdir() if d.is_dir()] if runs_root.exists() else []
        if not candidates:
            raise FileNotFoundError(f"No runs found in {runs_root}")
        return max(candidates, key=lambda d: d.stat().st_mtime)

    # Try direct match
    direct = runs_root / run_id.removeprefix("run-")
    if direct.exists():
        return direct

    # Try by_run_id symlink
    by_id = runs_root / "by_run_id" / run_id
    if by_id.exists() and by_id.is_symlink():
        return by_id.resolve()

    raise FileNotFoundError(f"Run '{run_id}' not found in {runs_root}")


def _cmd_report(
    run_id: str,
    *,
    project: str,
    format: str,
    output: str | None,
) -> int:
    """Regenerate report from a previous run."""
    from snowl.aggregator import (
        aggregate_benchmark_rows,
        aggregate_domain_rows,
        aggregate_leaderboard_rows,
        aggregate_outcomes,
    )
    from snowl.report.html import render_report
    from snowl.artifacts import build_benchmark_metadata_map

    try:
        run_dir = _resolve_run_dir(run_id, project)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    # Load outcomes
    outcomes_path = run_dir / "outcomes.json"
    if not outcomes_path.exists():
        print(f"Error: No outcomes.json in {run_dir}")
        return 1

    with outcomes_path.open("r", encoding="utf-8") as f:
        raw_outcomes = json.load(f)

    # Load aggregate
    aggregate_path = run_dir / "aggregate.json"
    if not aggregate_path.exists():
        print(f"Error: No aggregate.json in {run_dir}")
        return 1

    with aggregate_path.open("r", encoding="utf-8") as f:
        raw_aggregate = json.load(f)

    # Load diagnostics
    diagnostics_path = run_dir / "diagnostics_index.json"
    diagnostics_index = []
    if diagnostics_path.exists():
        with diagnostics_path.open("r", encoding="utf-8") as f:
            diagnostics_index = json.load(f)

    # Load summary
    summary_path = run_dir / "summary.json"
    summary_data = {}
    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8") as f:
            summary_data = json.load(f)

    # Build lightweight summary/aggregate objects for rendering
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

    summary = _Summary(summary_data)
    aggregate = _Aggregate(raw_aggregate)

    # Load manifest for benchmark name
    manifest_path = run_dir / "manifest.json"
    benchmark_name = None
    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
            benchmark_name = manifest.get("benchmark")

    benchmark_metadata_map = build_benchmark_metadata_map(benchmark_name)

    if format == "json":
        json.dump(raw_aggregate, sys.stdout, ensure_ascii=False, indent=2)
        return 0

    if format == "markdown":
        lines = ["# Snowl Report", ""]
        lines.append(f"**Total**: {summary.total} | **Success**: {summary.success} | **Error**: {summary.error}")
        lines.append("")
        lines.append("## Metrics")
        lines.append("")
        lines.append("| Task | Agent | Metrics |")
        lines.append("|------|-------|---------|")
        for task_id in sorted(aggregate.matrix.keys()):
            agents = aggregate.matrix[task_id]
            for agent_id in sorted(agents.keys()):
                metrics = agents[agent_id]
                metric_text = ", ".join(f"{k}: {v:.3f}" for k, v in sorted(metrics.items()))
                lines.append(f"| {task_id} | {agent_id} | {metric_text} |")
        lines.append("")
        sys.stdout.write("\n".join(lines) + "\n")
        return 0

    # format == "html"
    benchmark_rows = None
    domain_rows = None
    leaderboard_rows = None
    try:
        from snowl.runtime.results import outcome_from_serialized
        outcomes = [outcome_from_serialized(o) for o in raw_outcomes]
        benchmark_rows = aggregate_benchmark_rows(outcomes, benchmark_metadata_map)
        domain_rows = aggregate_domain_rows(benchmark_rows)
        leaderboard_rows = aggregate_leaderboard_rows(benchmark_rows)
    except Exception:
        pass  # Fall back to V1-only report

    html = render_report(
        summary=summary,
        aggregate=aggregate,
        diagnostics_index=diagnostics_index,
        benchmark_rows=benchmark_rows,
        domain_rows=domain_rows,
        leaderboard_rows=leaderboard_rows,
        run_id=run_id if run_id != "latest" else "",
    )

    if output:
        Path(output).write_text(html, encoding="utf-8")
        print(f"Report written to {output}")
    else:
        report_path = run_dir / "report.html"
        report_path.write_text(html, encoding="utf-8")
        print(f"Report written to {report_path}")

    return 0


def _cmd_compare(
    run_id_a: str,
    run_id_b: str,
    *,
    project: str,
    format: str,
    output: str | None,
) -> int:
    """Compare results from two runs."""
    from snowl.report.compare import compare_runs

    try:
        run_dir_a = _resolve_run_dir(run_id_a, project)
        run_dir_b = _resolve_run_dir(run_id_b, project)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    # Load aggregate data
    def _load_aggregate(run_dir: Path) -> dict:
        agg_path = run_dir / "aggregate.json"
        if not agg_path.exists():
            print(f"Error: No aggregate.json in {run_dir}")
            raise SystemExit(1)
        with agg_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _load_benchmark_summary(run_dir: Path) -> list[dict]:
        bs_path = run_dir / "benchmark_summary.json"
        if not bs_path.exists():
            return []
        with bs_path.open("r", encoding="utf-8") as f:
            return json.load(f).get("rows", [])

    agg_a = _load_aggregate(run_dir_a)
    agg_b = _load_aggregate(run_dir_b)
    bs_a = _load_benchmark_summary(run_dir_a)
    bs_b = _load_benchmark_summary(run_dir_b)

    diff = compare_runs(agg_a, agg_b, benchmark_rows_a=bs_a, benchmark_rows_b=bs_b)

    if format == "json":
        json.dump(diff, sys.stdout, ensure_ascii=False, indent=2)
    elif format == "html":
        from snowl.report.compare import render_compare_html
        html = render_compare_html(diff, run_id_a=run_id_a, run_id_b=run_id_b)
        if output:
            Path(output).write_text(html, encoding="utf-8")
            print(f"Compare report written to {output}")
        else:
            sys.stdout.write(html)
    else:
        # markdown
        lines = [f"# Compare: {run_id_a} vs {run_id_b}", ""]
        summary = diff.get("summary", {})
        lines.append(f"Improved: {summary.get('improved', 0)} | Regressed: {summary.get('regressed', 0)} | Unchanged: {summary.get('unchanged', 0)}")
        lines.append("")
        deltas = diff.get("deltas", [])
        if deltas:
            lines.append("| Key | Metric | A | B | Delta | Direction |")
            lines.append("|-----|--------|---|---|-------|-----------|")
            for d in deltas:
                lines.append(f"| {d['key']} | {d['metric']} | {d['value_a']:.4f} | {d['value_b']:.4f} | {d['delta']:+.4f} | {d['direction']} |")
        sys.stdout.write("\n".join(lines) + "\n")

    return 0


def _cmd_rescore(
    run_id: str,
    *,
    project: str,
    scorer: str | None,
) -> int:
    """Re-score trials from a previous run."""
    from snowl.rescore import rescore_run

    try:
        run_dir = _resolve_run_dir(run_id, project)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    scorer_filter = [s.strip() for s in scorer.split(",") if s.strip()] if scorer else None

    try:
        asyncio.run(rescore_run(run_dir=run_dir, scorer_filter=scorer_filter))
        print(f"Rescoring complete for {run_dir}")
        return 0
    except Exception as exc:
        print(f"Rescore failed: {exc}")
        return 1


def _cmd_export(
    run_id: str,
    *,
    project: str,
    format: str,
    output: str | None,
    trial_key: str | None,
) -> int:
    """Export trial trace data in portable formats."""
    from snowl.export.openai_trace import outcome_to_openai_conversation

    try:
        run_dir = _resolve_run_dir(run_id, project)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    # Load outcomes
    outcomes = _load_outcomes(run_dir)
    if not outcomes:
        print("No trial outcomes found.")
        return 1

    # Filter by trial key if specified
    if trial_key:
        filtered = []
        for outcome in outcomes:
            tr = outcome.get("task_result", {}) or {}
            task_id = str(tr.get("task_id", ""))
            agent_id = str(tr.get("agent_id", ""))
            sample_id = str(tr.get("sample_id", ""))
            payload = tr.get("payload", {}) or {}
            variant_id = str(payload.get("variant_id", "")) if isinstance(payload, dict) else ""
            key = "::".join(part for part in [task_id, agent_id, variant_id, sample_id] if part)
            if key == trial_key:
                filtered.append(outcome)
        outcomes = filtered
        if not outcomes:
            print(f"No trial found matching key: {trial_key}")
            return 1

    # Format output
    if format == "openai":
        exported = [outcome_to_openai_conversation(o) for o in outcomes]
        text = json.dumps(exported, indent=2, ensure_ascii=False)
    elif format == "json":
        text = json.dumps(outcomes, indent=2, ensure_ascii=False)
    elif format == "jsonl":
        lines = [json.dumps(o, ensure_ascii=False) for o in outcomes]
        text = "\n".join(lines)
    else:
        print(f"Unsupported format: {format}")
        return 1

    # Write output
    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(f"Exported {len(outcomes)} trial(s) to {output}")
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")

    return 0


def _load_outcomes(run_dir: Path) -> list[dict[str, Any]]:
    """Load trial outcomes from a run directory."""
    # Try trials.jsonl first
    trials_jsonl = run_dir / "trials.jsonl"
    if trials_jsonl.is_file():
        outcomes = []
        for line in trials_jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                outcomes.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if outcomes:
            return outcomes

    # Fallback to outcomes.json
    outcomes_json = run_dir / "outcomes.json"
    if outcomes_json.is_file():
        try:
            with outcomes_json.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass

    return []
