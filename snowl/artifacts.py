"""Run artifact persistence for eval control-plane code."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from snowl.aggregator import (
    AGGREGATE_SCHEMA_URI,
    BENCHMARK_SUMMARY_SCHEMA_URI,
    DOMAIN_SUMMARY_SCHEMA_URI,
    RESULT_SCHEMA_URI,
    RESULT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION_V2,
    aggregate_benchmark_rows,
    aggregate_domain_rows,
    aggregate_leaderboard_rows,
    aggregate_outcomes,
)
from snowl.observability.events import utc_iso_from_ms
from snowl.planning import EvalPlan, trial_models
from snowl.runtime import TrialOutcome
from snowl.runtime.results import to_serializable_outcome


class RunArtifactStore:
    """Persist live and final run artifacts using the current public shapes.

    The store owns filenames and JSON/JSONL/CSV payload construction. It does
    not decide scheduling, retry semantics, or event ordering.
    """

    def __init__(self, *, base_dir: Path, run_id: str, out_dir: Path | None = None) -> None:
        self.base_dir = base_dir
        self.run_id = run_id
        self.out_dir = out_dir

    def write_live_metadata(
        self,
        *,
        out_dir: Path,
        experiment_id: str,
        benchmark: str,
        plan: EvalPlan,
        task_monitor: Any,
        controls: dict[str, Any],
        trial_count: int,
        event_stream_mode: str,
        manifest_extra: dict[str, Any] | None = None,
    ) -> None:
        model_by_trial_key = trial_models(plan)
        _write_json_file(
            out_dir / "plan.json",
            {
                "mode": plan.mode,
                "task_ids": plan.task_ids,
                "agent_ids": plan.agent_ids,
                "variant_ids": plan.variant_ids,
                "sample_count": plan.sample_count,
                "trial_count": trial_count,
            },
        )
        manifest_payload = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "result_schema_uri": RESULT_SCHEMA_URI,
            "aggregate_schema_uri": AGGREGATE_SCHEMA_URI,
            "run_id": self.run_id,
            "experiment_id": experiment_id,
            "benchmark": benchmark,
            "event_stream_mode": event_stream_mode,
            "status": "running",
            "runtime_state": "runtime_state.json",
            "research_exports": {
                "events_jsonl": "events.jsonl",
            },
        }
        if manifest_extra:
            manifest_payload.update(dict(manifest_extra))
        _write_json_file(out_dir / "manifest.json", manifest_payload)
        _write_json_file(
            out_dir / "profiling.json",
            {
                "run": {
                    "run_id": self.run_id,
                    "experiment_id": experiment_id,
                    "benchmark": benchmark,
                },
                "controls": controls,
                "throughput": {
                    "trial_count": trial_count,
                },
                "task_monitor": task_monitor_rows(task_monitor, model_by_trial_key=model_by_trial_key),
            },
        )

    def update_manifest_status(
        self,
        out_dir: Path,
        *,
        status: str,
        ended_ts_ms: int | None = None,
        termination_reason: str | None = None,
    ) -> None:
        manifest_path = out_dir / "manifest.json"
        manifest: dict[str, Any] = {}
        try:
            raw = manifest_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                manifest = dict(parsed)
        except Exception:
            manifest = {}
        manifest["status"] = status
        if ended_ts_ms is not None:
            manifest["ended_at_ts_ms"] = int(ended_ts_ms)
            manifest["ended_at_utc"] = utc_iso_from_ms(int(ended_ts_ms))
        if termination_reason:
            manifest["termination_reason"] = str(termination_reason)
        _write_json_file(manifest_path, manifest)

    def write_final(
        self,
        *,
        outcomes: list[TrialOutcome],
        plan: EvalPlan,
        summary: Any,
        rerun_command: str,
        out_dir: Path,
        run_log_lines: list[str] | None = None,
        event_rows: list[dict[str, Any]] | None = None,
        profiling: dict[str, Any] | None = None,
        experiment_id: str | None = None,
        event_stream_mode: str = "batch_write",
        manifest_extra: dict[str, Any] | None = None,
    ) -> Path:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        _write_json_file(
            out_dir / "plan.json",
            {
                "mode": plan.mode,
                "task_ids": plan.task_ids,
                "agent_ids": plan.agent_ids,
                "variant_ids": plan.variant_ids,
                "sample_count": plan.sample_count,
                "trial_count": len(plan.trials),
            },
        )
        _write_json_file(out_dir / "summary.json", dict(summary.__dict__))

        aggregate = aggregate_outcomes(outcomes)
        _write_json_file(
            out_dir / "aggregate.json",
            {
                "schema_uri": AGGREGATE_SCHEMA_URI,
                "schema_version": RESULT_SCHEMA_VERSION,
                "by_task_agent": aggregate.by_task_agent,
                "matrix": aggregate.matrix,
            },
        )

        benchmark_name = (profiling or {}).get("run", {}).get("benchmark") if isinstance(profiling, dict) else None
        benchmark_metadata_map = build_benchmark_metadata_map(benchmark_name)

        benchmark_rows = aggregate_benchmark_rows(outcomes, benchmark_metadata_map)
        _write_json_file(
            out_dir / "benchmark_summary.json",
            {
                "schema_uri": BENCHMARK_SUMMARY_SCHEMA_URI,
                "schema_version": RESULT_SCHEMA_VERSION_V2,
                "rows": [r.to_dict() for r in benchmark_rows],
            },
        )

        domain_rows = aggregate_domain_rows(benchmark_rows)
        _write_json_file(
            out_dir / "domain_summary.json",
            {
                "schema_uri": DOMAIN_SUMMARY_SCHEMA_URI,
                "schema_version": RESULT_SCHEMA_VERSION_V2,
                "rows": [r.to_dict() for r in domain_rows],
            },
        )

        leaderboard_rows = aggregate_leaderboard_rows(benchmark_rows)
        with (out_dir / "leaderboard_rows.jsonl").open("w", encoding="utf-8") as f:
            for row in leaderboard_rows:
                f.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")

        _write_json_file(
            out_dir / "outcomes.json",
            [
                to_serializable_outcome(
                    o,
                    schema_version=RESULT_SCHEMA_VERSION,
                    schema_uri=RESULT_SCHEMA_URI,
                )
                for o in outcomes
            ],
        )

        with (out_dir / "trials.jsonl").open("w", encoding="utf-8") as f:
            for idx, outcome in enumerate(outcomes, start=1):
                row = to_serializable_outcome(
                    outcome,
                    schema_version=RESULT_SCHEMA_VERSION,
                    schema_uri=RESULT_SCHEMA_URI,
                )
                row["run_id"] = self.run_id
                row["schema_version"] = RESULT_SCHEMA_VERSION
                row["trial_index"] = idx
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        if event_rows is not None:
            with (out_dir / "events.jsonl").open("w", encoding="utf-8") as f:
                for idx, row in enumerate(event_rows or [], start=1):
                    row_dict = dict(row)
                    event_index = int(row_dict.get("event_index") or idx)
                    event_id = str(row_dict.get("event_id") or f"{self.run_id}:{event_index}")
                    event_row = {
                        "schema_version": RESULT_SCHEMA_VERSION,
                        "run_id": self.run_id,
                        "event_index": event_index,
                        "seq": event_index,
                        "event_id": event_id,
                        **row_dict,
                    }
                    event_row["run_id"] = self.run_id
                    event_row["event_index"] = event_index
                    event_row["seq"] = event_index
                    event_row["event_id"] = event_id
                    f.write(json.dumps(event_row, ensure_ascii=False) + "\n")

        self._write_metrics_wide(out_dir=out_dir, outcomes=outcomes)
        diagnostics_index = self._write_diagnostics(out_dir=out_dir, outcomes=outcomes)
        manifest_payload = self._manifest_payload(
            now=now,
            summary=summary,
            rerun_command=rerun_command,
            diagnostics_index=diagnostics_index,
            event_stream_mode=event_stream_mode,
            profiling=profiling,
            experiment_id=experiment_id,
            benchmark_metadata_map=benchmark_metadata_map,
        )
        if manifest_extra:
            manifest_payload.update(dict(manifest_extra))
        _write_json_file(out_dir / "manifest.json", manifest_payload)
        (out_dir / "report.html").write_text(
            self._html_report(
                summary=summary,
                aggregate=aggregate,
                diagnostics_index=diagnostics_index,
                benchmark_rows=benchmark_rows,
                domain_rows=domain_rows,
                leaderboard_rows=leaderboard_rows,
            ),
            encoding="utf-8",
        )
        if run_log_lines is not None:
            (out_dir / "run.log").write_text(
                "\n".join(run_log_lines or []) + ("\n" if run_log_lines else ""),
                encoding="utf-8",
            )
        _write_json_file(out_dir / "profiling.json", profiling or {})
        return out_dir

    def _write_metrics_wide(self, *, out_dir: Path, outcomes: list[TrialOutcome]) -> None:
        metric_names = sorted({str(metric_name) for outcome in outcomes for metric_name in (outcome.scores or {}).keys()})
        fieldnames = [
            "schema_version",
            "run_id",
            "task_id",
            "agent_id",
            "variant_id",
            "sample_id",
            "status",
        ] + metric_names
        with (out_dir / "metrics_wide.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for outcome in outcomes:
                tr = outcome.task_result
                row: dict[str, Any] = {
                    "schema_version": RESULT_SCHEMA_VERSION,
                    "run_id": self.run_id,
                    "task_id": tr.task_id,
                    "agent_id": tr.agent_id,
                    "variant_id": str((tr.payload or {}).get("variant_id") or "default"),
                    "sample_id": tr.sample_id,
                    "status": tr.status.value,
                }
                for metric_name in metric_names:
                    score = (outcome.scores or {}).get(metric_name)
                    row[metric_name] = (float(score.value) if score is not None else "")
                writer.writerow(row)

    def _write_diagnostics(self, *, out_dir: Path, outcomes: list[TrialOutcome]) -> list[dict[str, Any]]:
        diagnostics_dir = out_dir / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        diagnostics_index: list[dict[str, Any]] = []
        for idx, outcome in enumerate(outcomes, start=1):
            sandbox = outcome.trace.get("sandbox") if isinstance(outcome.trace, dict) else None
            tr = outcome.task_result
            if not sandbox and tr.status.value not in {"error", "limit_exceeded", "cancelled"}:
                continue
            sample = tr.sample_id if tr.sample_id is not None else str(idx)
            variant_id = str((tr.payload or {}).get("variant_id") or "default")
            diag_name = f"{tr.task_id}__{tr.agent_id}__{variant_id}__{sample}.json"
            payload = {
                "task_id": tr.task_id,
                "agent_id": tr.agent_id,
                "variant_id": variant_id,
                "sample_id": tr.sample_id,
                "status": tr.status.value,
                "sandbox": sandbox,
                "error": tr.error.__dict__ if tr.error else None,
            }
            _write_json_file(diagnostics_dir / diag_name, payload)
            diagnostics_index.append(
                {
                    "task_id": tr.task_id,
                    "agent_id": tr.agent_id,
                    "variant_id": variant_id,
                    "sample_id": tr.sample_id,
                    "status": tr.status.value,
                    "path": f"diagnostics/{diag_name}",
                }
            )
        _write_json_file(out_dir / "diagnostics_index.json", diagnostics_index)
        return diagnostics_index

    def _manifest_payload(
        self,
        *,
        now: str,
        summary: Any,
        rerun_command: str,
        diagnostics_index: list[dict[str, Any]],
        event_stream_mode: str,
        profiling: dict[str, Any] | None,
        experiment_id: str | None,
        benchmark_metadata_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        benchmark_name = (profiling or {}).get("run", {}).get("benchmark") if isinstance(profiling, dict) else None
        payload = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "result_schema_uri": RESULT_SCHEMA_URI,
            "aggregate_schema_uri": AGGREGATE_SCHEMA_URI,
            "aggregation_schema_version": RESULT_SCHEMA_VERSION_V2,
            "run_id": self.run_id,
            "experiment_id": experiment_id,
            "benchmark": benchmark_name,
            "created_at_utc": now,
            "status": "completed",
            "rerun_command": rerun_command,
            "diagnostics_count": len(diagnostics_index),
            "event_stream_mode": event_stream_mode,
            "runtime_state": "runtime_state.json",
            "research_exports": {
                "trials_jsonl": "trials.jsonl",
                "events_jsonl": "events.jsonl",
                "metrics_wide_csv": "metrics_wide.csv",
                "benchmark_summary": "benchmark_summary.json",
                "domain_summary": "domain_summary.json",
                "leaderboard_rows": "leaderboard_rows.jsonl",
            },
        }
        if benchmark_name and benchmark_name in benchmark_metadata_map:
            bmeta = benchmark_metadata_map[benchmark_name]
            payload["benchmark_info"] = bmeta
            payload["domain"] = bmeta.get("domain", "uncategorized")
            payload["benchmark_type"] = bmeta.get("benchmark_type", "capability")
        _ = summary
        return payload

    def _html_report(
        self,
        *,
        summary: Any,
        aggregate: Any,
        diagnostics_index: list[dict[str, Any]],
        benchmark_rows: list[Any] | None = None,
        domain_rows: list[Any] | None = None,
        leaderboard_rows: list[Any] | None = None,
    ) -> str:
        from snowl.report.html import render_report
        return render_report(
            summary=summary,
            aggregate=aggregate,
            diagnostics_index=diagnostics_index,
            benchmark_rows=benchmark_rows,
            domain_rows=domain_rows,
            leaderboard_rows=leaderboard_rows,
            run_id=self.run_id,
        )


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_benchmark_metadata_map(benchmark_name: str | None) -> dict[str, dict[str, Any]]:
    from snowl.benchmarks.registry import get_default_benchmark_registry

    _ = benchmark_name
    result: dict[str, dict[str, Any]] = {}
    registry = get_default_benchmark_registry()
    for entry in registry.list():
        result[entry.info.name] = asdict(entry.info)
    return result


def task_monitor_rows(task_monitor: Any, *, model_by_trial_key: dict[str, str | None] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "task_id": state.task_id,
            "agent_id": state.agent_id,
            "variant_id": state.variant_id,
            "sample_id": state.sample_id,
            "model": (model_by_trial_key or {}).get(state.key),
            "status": state.status.value,
            "step_count": state.step_count,
            "duration_ms": state.duration_ms,
            "latest_action": state.latest_action,
            "latest_observation": state.latest_observation,
            "latest_message": state.latest_message,
            "scorer_metrics": dict(state.scorer_metrics),
        }
        for state in task_monitor.list_states()
    ]
