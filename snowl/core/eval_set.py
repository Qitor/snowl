"""Eval set: manage groups of eval runs with retry and resume support.

Framework role:
- Provides a named collection of eval runs with cross-run accumulation
  and automatic retry of failed samples.
- Wraps the existing dispatch checkpoint/resume infrastructure into a
  higher-level API.

Runtime/usage wiring:
- Used by CLI `snowl run --eval-set <name> --retry-failed`.
- Can also be used programmatically for multi-run evaluation workflows.

Change guardrails:
- EvalSet is a stateless coordinator; actual run state is persisted by
  dispatch checkpoints. This module only tracks run metadata.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from snowl.errors import SnowlValidationError


@dataclass(frozen=True)
class EvalRunRef:
    """Lightweight reference to a completed or in-progress eval run."""
    run_id: str
    timestamp: float
    artifacts_dir: str
    status: str = "completed"  # completed | partial | failed
    total_trials: int = 0
    success_count: int = 0
    error_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalSet:
    """Named collection of eval runs with retry/resume support.

    Usage::

        eval_set = EvalSet(name="swe-bench-v2")
        eval_set.add_run(ref)
        failed = eval_set.failed_run_ids()
        retry_ref = eval_set.retry_failed(latest_run_id)
    """
    name: str
    runs: list[EvalRunRef] = field(default_factory=list)

    def add_run(self, ref: EvalRunRef) -> None:
        """Record a run in this eval set."""
        self.runs.append(ref)

    @property
    def latest_run(self) -> EvalRunRef | None:
        """The most recent run in the set, or None."""
        return self.runs[-1] if self.runs else None

    def failed_run_ids(self) -> list[str]:
        """Return run IDs that have any error trials."""
        return [r.run_id for r in self.runs if r.error_count > 0 or r.status in ("partial", "failed")]

    def cumulative_summary(self) -> dict[str, Any]:
        """Aggregate stats across all runs in the set."""
        total_trials = sum(r.total_trials for r in self.runs)
        total_success = sum(r.success_count for r in self.runs)
        total_errors = sum(r.error_count for r in self.runs)
        return {
            "eval_set": self.name,
            "run_count": len(self.runs),
            "total_trials": total_trials,
            "total_success": total_success,
            "total_errors": total_errors,
            "success_rate": total_success / total_trials if total_trials > 0 else 0.0,
        }

    def retry_failed(self, latest_run_id: str | None = None) -> EvalRunRef | None:
        """Create a retry reference for the latest (or specified) run's failed trials.

        Returns an EvalRunRef with status="retry" or None if no failed run found.
        The caller is responsible for actually executing the retry via dispatch.
        """
        target = None
        if latest_run_id is not None:
            for r in self.runs:
                if r.run_id == latest_run_id:
                    target = r
                    break
        else:
            target = self.latest_run

        if target is None:
            return None

        if target.error_count == 0 and target.status == "completed":
            return None

        return EvalRunRef(
            run_id=f"retry-{target.run_id}-{int(time.time())}",
            timestamp=time.time(),
            artifacts_dir=target.artifacts_dir,
            status="retry",
            total_trials=target.error_count,
            success_count=0,
            error_count=0,
            metadata={"retry_of": target.run_id},
        )

    def resume(self, previous_run_id: str | None = None) -> EvalRunRef | None:
        """Create a resume reference for an incomplete run.

        Returns an EvalRunRef with status="resume" or None if the run is complete.
        """
        target = None
        if previous_run_id is not None:
            for r in self.runs:
                if r.run_id == previous_run_id:
                    target = r
                    break
        else:
            # Find the latest non-completed run
            for r in reversed(self.runs):
                if r.status in ("partial", "failed"):
                    target = r
                    break

        if target is None:
            return None

        if target.status == "completed":
            return None

        return EvalRunRef(
            run_id=f"resume-{target.run_id}-{int(time.time())}",
            timestamp=time.time(),
            artifacts_dir=target.artifacts_dir,
            status="resume",
            total_trials=target.total_trials - target.success_count,
            success_count=0,
            error_count=0,
            metadata={"resume_of": target.run_id},
        )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _eval_set_path(base_dir: Path, name: str) -> Path:
    return base_dir / ".snowl" / "eval_sets" / f"{name}.json"


def save_eval_set(eval_set: EvalSet, base_dir: Path) -> None:
    """Persist an EvalSet to disk."""
    path = _eval_set_path(base_dir, eval_set.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "name": eval_set.name,
        "runs": [
            {
                "run_id": r.run_id,
                "timestamp": r.timestamp,
                "artifacts_dir": r.artifacts_dir,
                "status": r.status,
                "total_trials": r.total_trials,
                "success_count": r.success_count,
                "error_count": r.error_count,
                "metadata": r.metadata,
            }
            for r in eval_set.runs
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_eval_set(base_dir: Path, name: str) -> EvalSet:
    """Load an EvalSet from disk. Raises FileNotFoundError if not found."""
    path = _eval_set_path(base_dir, name)
    if not path.exists():
        raise FileNotFoundError(f"EvalSet '{name}' not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = [
        EvalRunRef(
            run_id=r["run_id"],
            timestamp=r["timestamp"],
            artifacts_dir=r["artifacts_dir"],
            status=r.get("status", "completed"),
            total_trials=r.get("total_trials", 0),
            success_count=r.get("success_count", 0),
            error_count=r.get("error_count", 0),
            metadata=r.get("metadata", {}),
        )
        for r in data.get("runs", [])
    ]
    return EvalSet(name=data["name"], runs=runs)
