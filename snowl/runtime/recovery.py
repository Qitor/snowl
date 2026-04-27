"""Recovery ledger and retry-attempt bookkeeping for eval runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from snowl.planning import PlanTrial
from snowl.runtime import TrialOutcome
from snowl.runtime.results import (
    classify_failure_from_serialized,
    outcome_from_serialized,
    to_serializable_outcome,
    trial_key_from_task_result_dict,
)


class RecoveryManager:
    """Manage the run recovery ledger and effective attempt rows.

    Recovery is still whole-trial based. This manager records attempts and
    effective outcomes; it does not choose queue order or introduce phase-level
    retry semantics.
    """

    def __init__(
        self,
        *,
        run_dir: Path,
        run_id: str,
        schema_version: str,
        schema_uri: str,
    ) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self.schema_version = schema_version
        self.schema_uri = schema_uri
        self.state = self._bootstrap_state()

    @property
    def recovery_path(self) -> Path:
        return self.run_dir / "recovery.json"

    @property
    def attempts_jsonl_path(self) -> Path:
        return self.run_dir / "attempts.jsonl"

    def effective_rows(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        attempts_by_trial = self.state.get("attempts_by_trial") or {}
        effective_attempts = self.state.get("effective_attempts") or {}
        if not isinstance(attempts_by_trial, dict) or not isinstance(effective_attempts, dict):
            return out
        for trial_key, bucket in attempts_by_trial.items():
            if not isinstance(bucket, list):
                continue
            effective_id = str(effective_attempts.get(trial_key) or "").strip()
            for row in bucket:
                if not isinstance(row, dict):
                    continue
                if effective_id and str(row.get("attempt_id") or "") == effective_id:
                    out[str(trial_key)] = dict(row)
                    break
        return out

    def write(self) -> None:
        self.recovery_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_attempts_jsonl()

    def outcome_from_attempt_row(self, row: dict[str, Any]) -> TrialOutcome:
        return outcome_from_serialized(
            {
                "task_result": row.get("task_result") or {},
                "scores": row.get("scores") or {},
                "trace": row.get("trace") or {},
            }
        )

    def auto_retry_count(self, trial_key: str) -> int:
        bucket = ((self.state.get("attempts_by_trial") or {}).get(trial_key) or [])
        if not isinstance(bucket, list):
            return 0
        return sum(
            1
            for row in bucket
            if isinstance(row, dict) and str(row.get("retry_source") or "") == "auto_retry"
        )

    def record_attempt(
        self,
        *,
        effective_rows: dict[str, dict[str, Any]],
        key: str,
        trial: PlanTrial,
        outcome: TrialOutcome,
        retry_source: str,
        current_effective_outcomes: dict[str, TrialOutcome],
    ) -> dict[str, Any]:
        previous = effective_rows.get(key)
        previous_attempt_id = str((previous or {}).get("attempt_id") or "").strip() or None
        attempts_by_trial = self.state.setdefault("attempts_by_trial", {})
        attempts_by_trial.setdefault(key, [])
        bucket = attempts_by_trial.get(key)
        attempt_no = len(bucket) + 1 if isinstance(bucket, list) else 1
        serializable = to_serializable_outcome(
            outcome,
            schema_version=self.schema_version,
            schema_uri=self.schema_uri,
        )
        failure_class = classify_failure_from_serialized(serializable)
        task_result = dict(serializable.get("task_result") or {})
        payload = dict(task_result.get("payload") or {})
        timing = dict(task_result.get("timing") or {})
        started_ts = timing.get("started_at_ms")
        ended_ts = timing.get("ended_at_ms")
        attempt_row = {
            "attempt_id": f"{key}::attempt-{attempt_no:04d}",
            "attempt_no": attempt_no,
            "trial_key": key,
            "task_id": task_result.get("task_id"),
            "agent_id": task_result.get("agent_id"),
            "variant_id": payload.get("variant_id") or trial.variant_id,
            "sample_id": task_result.get("sample_id"),
            "model": payload.get("model") or trial.model,
            "status": task_result.get("status"),
            "failure_class": failure_class,
            "effective": True,
            "supersedes_attempt_id": previous_attempt_id,
            "superseded_by_attempt_id": None,
            "started_ts_ms": started_ts,
            "ended_ts_ms": ended_ts,
            "duration_ms": (
                max(0, int(ended_ts) - int(started_ts))
                if started_ts is not None and ended_ts is not None
                else None
            ),
            "retry_source": retry_source,
            "task_result": task_result,
            "scores": dict(serializable.get("scores") or {}),
            "trace": dict(serializable.get("trace") or {}),
        }
        if isinstance(attempts_by_trial[key], list):
            for row in attempts_by_trial[key]:
                if isinstance(row, dict):
                    row["effective"] = False
                    if previous_attempt_id and str(row.get("attempt_id") or "") == previous_attempt_id:
                        row["superseded_by_attempt_id"] = attempt_row["attempt_id"]
            attempts_by_trial[key].append(attempt_row)
        self.state.setdefault("effective_attempts", {})[key] = attempt_row["attempt_id"]
        effective_rows[key] = attempt_row
        current_effective_outcomes[key] = outcome
        return attempt_row

    def _bootstrap_state(self) -> dict[str, Any]:
        existing = _read_json_file(self.recovery_path, default=None)
        if isinstance(existing, dict) and existing.get("run_id") == self.run_id:
            existing.setdefault("attempts_by_trial", {})
            existing.setdefault("effective_attempts", {})
            existing.setdefault("sessions", [])
            existing.setdefault("next_attempt_no", 1)
            return existing

        outcomes = _read_json_file(self.run_dir / "outcomes.json", default=[])
        attempts_by_trial: dict[str, list[dict[str, Any]]] = {}
        effective_attempts: dict[str, str] = {}
        next_attempt_no = 1
        for row in outcomes if isinstance(outcomes, list) else []:
            if not isinstance(row, dict):
                continue
            task_result = dict(row.get("task_result") or {})
            trial_key = trial_key_from_task_result_dict(task_result)
            if not trial_key:
                continue
            attempt_no = int(row.get("attempt_no") or 1)
            attempt_id = str(row.get("attempt_id") or f"{trial_key}::attempt-{attempt_no:04d}")
            payload = dict(task_result.get("payload") or {})
            started_ts = None
            ended_ts = None
            timing = dict(task_result.get("timing") or {})
            if timing:
                started_ts = timing.get("started_at_ms")
                ended_ts = timing.get("ended_at_ms")
            attempt_row = {
                "attempt_id": attempt_id,
                "attempt_no": attempt_no,
                "trial_key": trial_key,
                "task_id": task_result.get("task_id"),
                "agent_id": task_result.get("agent_id"),
                "variant_id": payload.get("variant_id") or "default",
                "sample_id": task_result.get("sample_id"),
                "model": payload.get("model"),
                "status": task_result.get("status"),
                "failure_class": classify_failure_from_serialized(row),
                "effective": True,
                "supersedes_attempt_id": None,
                "superseded_by_attempt_id": None,
                "started_ts_ms": started_ts,
                "ended_ts_ms": ended_ts,
                "duration_ms": (
                    max(0, int(ended_ts) - int(started_ts))
                    if started_ts is not None and ended_ts is not None
                    else None
                ),
                "retry_source": "initial_run",
                "task_result": task_result,
                "scores": dict(row.get("scores") or {}),
                "trace": dict(row.get("trace") or {}),
            }
            attempts_by_trial.setdefault(trial_key, []).append(attempt_row)
            effective_attempts[trial_key] = attempt_id
            next_attempt_no = max(next_attempt_no, attempt_no + 1)

        recovery = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "attempts_by_trial": attempts_by_trial,
            "effective_attempts": effective_attempts,
            "sessions": [],
            "next_attempt_no": next_attempt_no,
        }
        self.recovery_path.write_text(json.dumps(recovery, ensure_ascii=False, indent=2), encoding="utf-8")
        self.state = recovery
        self._write_attempts_jsonl()
        return recovery

    def _write_attempts_jsonl(self) -> None:
        rows: list[dict[str, Any]] = []
        attempts_by_trial = self.state.get("attempts_by_trial") or {}
        if isinstance(attempts_by_trial, dict):
            for bucket in attempts_by_trial.values():
                if isinstance(bucket, list):
                    for row in bucket:
                        if isinstance(row, dict):
                            rows.append(dict(row))
        rows.sort(key=lambda row: (str(row.get("trial_key") or ""), int(row.get("attempt_no") or 0)))
        with self.attempts_jsonl_path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def attempt_status_from_outcome(outcome: TrialOutcome) -> str:
    return str(outcome.task_result.status.value or "").strip().lower()


def attempt_is_success(outcome: TrialOutcome) -> bool:
    return attempt_status_from_outcome(outcome) == "success"


def recovery_retry_allowed(outcome: TrialOutcome) -> bool:
    return not attempt_is_success(outcome)


def _read_json_file(path: Path, *, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
