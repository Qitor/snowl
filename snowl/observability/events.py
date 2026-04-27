"""Run event persistence and runtime-state heartbeat support."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from snowl.planning import PlanTrial, trial_key as make_trial_key


def utc_iso_from_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def pick_event_value(event: dict[str, Any], key: str) -> Any:
    if key in event and event.get(key) is not None:
        return event.get(key)
    payload = event.get("payload")
    if isinstance(payload, dict):
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
        nested = payload.get("payload")
        if isinstance(nested, dict):
            return nested.get(key)
    return None


def count_existing_events(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except Exception:
        return 0


class LiveRunStateWriter:
    def __init__(
        self,
        *,
        path: Path,
        run_id: str,
        experiment_id: str,
        benchmark: str,
        started_ts_ms: int,
        owner_pid: int | None = None,
    ) -> None:
        self._path = path
        self._lock = threading.Lock()
        pid = int(owner_pid or os.getpid())
        self._state: dict[str, Any] = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "benchmark": benchmark,
            "status": "running",
            "owner_pid": pid,
            "started_ts_ms": int(started_ts_ms),
            "started_at_utc": utc_iso_from_ms(int(started_ts_ms)),
            "heartbeat_ts_ms": int(started_ts_ms),
            "last_event_ts_ms": int(started_ts_ms),
            "last_progress_ts_ms": None,
            "ended_ts_ms": None,
            "termination_reason": None,
        }
        self._flush_locked()

    def _flush_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._path)

    def heartbeat(self, *, ts_ms: int | None = None) -> None:
        with self._lock:
            if self._state.get("status") != "running":
                return
            heartbeat_ts = int(ts_ms or int(datetime.now(timezone.utc).timestamp() * 1000))
            self._state["heartbeat_ts_ms"] = heartbeat_ts
            self._flush_locked()

    def record_event(self, *, ts_ms: int | None = None, progress: bool = False) -> None:
        with self._lock:
            if self._state.get("status") != "running":
                return
            event_ts = int(ts_ms or int(datetime.now(timezone.utc).timestamp() * 1000))
            self._state["heartbeat_ts_ms"] = max(int(self._state.get("heartbeat_ts_ms") or 0), event_ts)
            self._state["last_event_ts_ms"] = max(int(self._state.get("last_event_ts_ms") or 0), event_ts)
            if progress:
                previous = self._state.get("last_progress_ts_ms")
                self._state["last_progress_ts_ms"] = max(int(previous or 0), event_ts)
            self._flush_locked()

    def mark_completed(self, *, ts_ms: int | None = None) -> None:
        with self._lock:
            ended_ts = int(ts_ms or int(datetime.now(timezone.utc).timestamp() * 1000))
            self._state["status"] = "completed"
            self._state["heartbeat_ts_ms"] = max(int(self._state.get("heartbeat_ts_ms") or 0), ended_ts)
            self._state["last_event_ts_ms"] = max(int(self._state.get("last_event_ts_ms") or 0), ended_ts)
            self._state["ended_ts_ms"] = ended_ts
            self._state["ended_at_utc"] = utc_iso_from_ms(ended_ts)
            self._state["termination_reason"] = "completed"
            self._flush_locked()

    def mark_cancelled(self, *, reason: str = "cancelled", ts_ms: int | None = None) -> None:
        with self._lock:
            ended_ts = int(ts_ms or int(datetime.now(timezone.utc).timestamp() * 1000))
            self._state["status"] = "cancelled"
            self._state["heartbeat_ts_ms"] = max(int(self._state.get("heartbeat_ts_ms") or 0), ended_ts)
            self._state["last_event_ts_ms"] = max(int(self._state.get("last_event_ts_ms") or 0), ended_ts)
            self._state["ended_ts_ms"] = ended_ts
            self._state["ended_at_utc"] = utc_iso_from_ms(ended_ts)
            self._state["termination_reason"] = str(reason or "cancelled")
            self._flush_locked()


class LiveEventsWriter:
    """Append-only live events writer with stable event ids."""

    def __init__(self, *, path: Path, run_id: str, schema_version: str, initial_event_index: int = 0) -> None:
        self._path = path
        self._run_id = run_id
        self._schema_version = schema_version
        self._lock = threading.Lock()
        self._event_index = max(0, int(initial_event_index))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._path.open("a", encoding="utf-8")

    def append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._event_index += 1
            idx = self._event_index
            event_id = str(row.get("event_id") or f"{self._run_id}:{idx}")
            event_row = {
                "schema_version": self._schema_version,
                "run_id": self._run_id,
                "event_index": idx,
                "seq": idx,
                "event_id": event_id,
                **dict(row),
            }
            event_row["event_index"] = idx
            event_row["seq"] = idx
            event_row["event_id"] = event_id
            event_row["run_id"] = self._run_id
            self._fh.write(json.dumps(event_row, ensure_ascii=False) + "\n")
            self._fh.flush()
            return event_row

    def close(self) -> None:
        with self._lock:
            try:
                self._fh.close()
            except Exception:
                pass


class RunEventBus:
    """Persist enriched run events and keep runtime_state.json fresh.

    The bus owns event ids, live append ordering, pretask synthetic events, and
    runtime heartbeat state. It does not schedule trials or render UI output.
    """

    def __init__(
        self,
        *,
        events_path: Path,
        runtime_state_path: Path,
        run_id: str,
        experiment_id: str,
        benchmark: str,
        started_ts_ms: int,
        schema_version: str,
        initial_event_index: int = 0,
    ) -> None:
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.benchmark = benchmark
        self.event_rows: list[dict[str, Any]] = []
        self._writer = LiveEventsWriter(
            path=events_path,
            run_id=run_id,
            schema_version=schema_version,
            initial_event_index=initial_event_index,
        )
        self._runtime_state = LiveRunStateWriter(
            path=runtime_state_path,
            run_id=run_id,
            experiment_id=experiment_id,
            benchmark=benchmark,
            started_ts_ms=started_ts_ms,
        )

    def append(self, row: dict[str, Any], *, trial: PlanTrial | None = None) -> list[dict[str, Any]]:
        enriched = enrich_event_row(
            row,
            run_id=self.run_id,
            experiment_id=self.experiment_id,
            trial=trial,
            benchmark_hint=self.benchmark,
        )
        persisted = self._writer.append(enriched)
        self._record_runtime_state(persisted)
        self.event_rows.append(dict(persisted))
        persisted_rows = [persisted]
        if trial is not None:
            for synthetic in derive_pretask_events(persisted):
                synthetic_enriched = enrich_event_row(
                    synthetic,
                    run_id=self.run_id,
                    experiment_id=self.experiment_id,
                    trial=trial,
                    benchmark_hint=self.benchmark,
                )
                persisted_synth = self._writer.append(synthetic_enriched)
                self._runtime_state.record_event(
                    ts_ms=int(persisted_synth.get("ts_ms") or int(datetime.now(timezone.utc).timestamp() * 1000)),
                    progress=False,
                )
                self.event_rows.append(dict(persisted_synth))
                persisted_rows.append(persisted_synth)
        return persisted_rows

    def heartbeat(self) -> None:
        self._runtime_state.heartbeat()

    def mark_completed(self, *, ts_ms: int | None = None) -> None:
        self._runtime_state.mark_completed(ts_ms=ts_ms)

    def mark_cancelled(self, *, reason: str, ts_ms: int | None = None) -> None:
        self._runtime_state.mark_cancelled(reason=reason, ts_ms=ts_ms)

    def close(self) -> None:
        self._writer.close()

    def _record_runtime_state(self, event: dict[str, Any]) -> None:
        event_name = str(event.get("event") or "").strip()
        progress_event_names = {
            "runtime.trial.start",
            "runtime.trial.finish",
            "runtime.trial.error",
            "runtime.scorer.start",
            "runtime.scorer.finish",
            "runtime.model.query.start",
            "runtime.model.query.finish",
            "runtime.agent.step",
        }
        self._runtime_state.record_event(
            ts_ms=int(event.get("ts_ms") or int(datetime.now(timezone.utc).timestamp() * 1000)),
            progress=event_name in progress_event_names,
        )


def enrich_event_row(
    raw_event: dict[str, Any],
    *,
    run_id: str,
    experiment_id: str,
    trial: PlanTrial | None,
    benchmark_hint: str | None,
) -> dict[str, Any]:
    row = dict(raw_event)
    task_id = str(
        row.get("task_id")
        or (trial.task_id if trial is not None else "")
        or pick_event_value(row, "task_id")
        or ""
    ).strip()
    agent_id = str(
        row.get("agent_id")
        or (trial.agent_id if trial is not None else "")
        or pick_event_value(row, "agent_id")
        or ""
    ).strip()
    variant_id = str(
        row.get("variant_id")
        or (trial.variant_id if trial is not None else "default")
        or pick_event_value(row, "variant_id")
        or "default"
    ).strip() or "default"
    sample_id_raw = (
        row.get("sample_id")
        or (trial.sample_id if trial is not None else None)
        or pick_event_value(row, "sample_id")
    )
    sample_id = (str(sample_id_raw).strip() if sample_id_raw is not None else "")
    model = str(
        row.get("model")
        or (trial.model if trial is not None else "")
        or pick_event_value(row, "model")
        or ""
    ).strip()
    benchmark = str(
        row.get("benchmark")
        or (trial.task.metadata.get("benchmark") if trial is not None and isinstance(trial.task.metadata, dict) else "")
        or pick_event_value(row, "benchmark")
        or benchmark_hint
        or "custom"
    ).strip().lower() or "custom"
    ts_raw = row.get("ts_ms")
    ts_ms = int(ts_raw) if isinstance(ts_raw, (int, float)) else int(datetime.now(timezone.utc).timestamp() * 1000)

    row_trial_key = row.get("trial_key")
    if not isinstance(row_trial_key, str) or not row_trial_key.strip():
        if trial is not None:
            row_trial_key = make_trial_key(trial)
        elif task_id and agent_id:
            sample_token = sample_id or "-"
            row_trial_key = f"{task_id}::{agent_id}::{variant_id}::{sample_token}"
        else:
            row_trial_key = ""

    row.update(
        {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "trial_key": row_trial_key,
            "benchmark": benchmark,
            "task_id": task_id or None,
            "agent_id": agent_id or None,
            "variant_id": variant_id,
            "model": model or None,
            "sample_id": sample_id or None,
            "ts_ms": ts_ms,
        }
    )
    return row


def derive_pretask_events(event: dict[str, Any]) -> list[dict[str, Any]]:
    name = str(event.get("event", "")).strip()
    if not name or name.startswith("pretask."):
        return []

    exit_code = pick_event_value(event, "exit_code")
    command_text = str(pick_event_value(event, "command_text") or "")
    command_text_l = command_text.lower()
    ready = pick_event_value(event, "ready")
    code = str(pick_event_value(event, "code") or "")

    def _status_from_exit(default_running: str = "running") -> str:
        if isinstance(exit_code, int):
            return "success" if exit_code == 0 else "failed"
        return default_running

    def _mk(stage_event: str, *, status: str, source: str) -> dict[str, Any]:
        out = {
            "event": stage_event,
            "phase": "env",
            "status": status,
            "message": status,
            "source_event": source,
        }
        for key in (
            "task_id",
            "agent_id",
            "variant_id",
            "sample_id",
            "trial_key",
            "model",
            "benchmark",
            "project",
            "compose_file",
            "command_text",
            "exit_code",
            "duration_ms",
            "ts_ms",
            "run_id",
            "experiment_id",
        ):
            value = pick_event_value(event, key)
            if value is not None:
                out[key] = value
        return out

    out: list[dict[str, Any]] = []

    if name.startswith("runtime.env.preflight."):
        status = "failed" if name.endswith(".error") else ("success" if name.endswith(".finish") or name.endswith(".hit") else "running")
        out.append(_mk("pretask.preflight", status=status, source=name))
        return out

    if "container.build" in name:
        out.append(_mk("pretask.build", status=_status_from_exit(), source=name))
        return out

    if name in {"runtime.env.command.start", "runtime.env.command.finish", "runtime.env.command.timeout"}:
        is_build = (" compose " in command_text_l and " build" in command_text_l) or command_text_l.startswith("docker compose") and " build" in command_text_l
        is_start = (
            (" compose " in command_text_l and " up" in command_text_l)
            or command_text_l.startswith("docker run")
            or (" compose " in command_text_l and " exec" in command_text_l and "tmux" in command_text_l)
        )
        if is_build:
            status = "running" if name.endswith(".start") else ("timeout" if name.endswith(".timeout") else _status_from_exit())
            out.append(_mk("pretask.build", status=status, source=name))
        if is_start:
            status = "running" if name.endswith(".start") else ("timeout" if name.endswith(".timeout") else _status_from_exit())
            out.append(_mk("pretask.start", status=status, source=name))
        return out

    if "container.starting" in name:
        out.append(_mk("pretask.start", status="running", source=name))
        return out

    if "container.started" in name:
        if isinstance(exit_code, int) and exit_code != 0:
            status = "failed"
        elif ready is False:
            status = "failed"
        else:
            status = "success"
        out.append(_mk("pretask.start", status=status, source=name))
        return out

    if "visual_probe" in name or name == "gui.container.wait":
        out.append(_mk("pretask.ready_probe", status="running", source=name))
        return out

    if "visual_ready" in name or name == "gui.container.ready":
        out.append(_mk("pretask.ready", status="success", source=name))
        return out

    if name == "runtime.trial.error" and code == "container_runtime_error":
        out.append(_mk("pretask.failed", status="failed", source=name))
        return out

    if "container.retry" in name:
        out.append(_mk("pretask.start", status="retry", source=name))
        return out

    return out
