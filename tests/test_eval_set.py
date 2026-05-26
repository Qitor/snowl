"""Tests for EvalSet, EvalRunRef, and persistence."""

import json
import pytest
from pathlib import Path

from snowl.core.eval_set import (
    EvalRunRef,
    EvalSet,
    load_eval_set,
    save_eval_set,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ref(run_id: str = "r1", **overrides) -> EvalRunRef:
    defaults = dict(
        run_id=run_id,
        timestamp=1000.0,
        artifacts_dir="/tmp/runs/r1",
        status="completed",
        total_trials=10,
        success_count=8,
        error_count=2,
    )
    defaults.update(overrides)
    return EvalRunRef(**defaults)


# ---------------------------------------------------------------------------
# EvalRunRef
# ---------------------------------------------------------------------------

class TestEvalRunRef:
    def test_creation(self):
        ref = _make_ref()
        assert ref.run_id == "r1"
        assert ref.total_trials == 10
        assert ref.success_count == 8

    def test_frozen(self):
        ref = _make_ref()
        with pytest.raises(AttributeError):
            ref.run_id = "changed"


# ---------------------------------------------------------------------------
# EvalSet
# ---------------------------------------------------------------------------

class TestEvalSet:
    def test_empty_set(self):
        es = EvalSet(name="test")
        assert es.latest_run is None
        assert es.failed_run_ids() == []

    def test_add_run(self):
        es = EvalSet(name="test")
        es.add_run(_make_ref())
        assert len(es.runs) == 1
        assert es.latest_run.run_id == "r1"

    def test_latest_run(self):
        es = EvalSet(name="test")
        es.add_run(_make_ref(run_id="r1"))
        es.add_run(_make_ref(run_id="r2"))
        assert es.latest_run.run_id == "r2"

    def test_failed_run_ids(self):
        es = EvalSet(name="test")
        es.add_run(_make_ref(run_id="r1", error_count=0, status="completed"))
        es.add_run(_make_ref(run_id="r2", error_count=3, status="partial"))
        assert es.failed_run_ids() == ["r2"]

    def test_failed_run_ids_includes_failed_status(self):
        es = EvalSet(name="test")
        es.add_run(_make_ref(run_id="r1", error_count=0, status="failed"))
        assert "r1" in es.failed_run_ids()

    def test_cumulative_summary(self):
        es = EvalSet(name="bench-v2")
        es.add_run(_make_ref(run_id="r1", total_trials=10, success_count=8, error_count=2))
        es.add_run(_make_ref(run_id="r2", total_trials=5, success_count=3, error_count=1))
        summary = es.cumulative_summary()
        assert summary["run_count"] == 2
        assert summary["total_trials"] == 15
        assert summary["total_success"] == 11
        assert summary["total_errors"] == 3
        assert abs(summary["success_rate"] - 11 / 15) < 1e-6

    def test_cumulative_summary_empty(self):
        es = EvalSet(name="empty")
        summary = es.cumulative_summary()
        assert summary["success_rate"] == 0.0

    def test_retry_failed_returns_ref(self):
        es = EvalSet(name="test")
        es.add_run(_make_ref(run_id="r1", error_count=3))
        retry = es.retry_failed()
        assert retry is not None
        assert retry.status == "retry"
        assert retry.metadata["retry_of"] == "r1"
        assert retry.total_trials == 3

    def test_retry_failed_specific_run(self):
        es = EvalSet(name="test")
        es.add_run(_make_ref(run_id="r1", error_count=0))
        es.add_run(_make_ref(run_id="r2", error_count=5))
        retry = es.retry_failed(latest_run_id="r2")
        assert retry is not None
        assert retry.metadata["retry_of"] == "r2"

    def test_retry_failed_no_errors(self):
        es = EvalSet(name="test")
        es.add_run(_make_ref(run_id="r1", error_count=0, status="completed"))
        assert es.retry_failed() is None

    def test_retry_failed_empty_set(self):
        es = EvalSet(name="test")
        assert es.retry_failed() is None

    def test_resume_partial_run(self):
        es = EvalSet(name="test")
        es.add_run(_make_ref(run_id="r1", status="partial", total_trials=10, success_count=5))
        resume = es.resume()
        assert resume is not None
        assert resume.status == "resume"
        assert resume.total_trials == 5  # remaining trials
        assert resume.metadata["resume_of"] == "r1"

    def test_resume_completed_returns_none(self):
        es = EvalSet(name="test")
        es.add_run(_make_ref(run_id="r1", status="completed"))
        assert es.resume() is None

    def test_resume_specific_run(self):
        es = EvalSet(name="test")
        es.add_run(_make_ref(run_id="r1", status="completed"))
        es.add_run(_make_ref(run_id="r2", status="partial", total_trials=10, success_count=3))
        resume = es.resume(previous_run_id="r2")
        assert resume is not None

    def test_resume_empty_set(self):
        es = EvalSet(name="test")
        assert es.resume() is None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestEvalSetPersistence:
    def test_save_and_load(self, tmp_path):
        es = EvalSet(name="my-set")
        es.add_run(_make_ref(run_id="r1"))
        save_eval_set(es, tmp_path)

        loaded = load_eval_set(tmp_path, "my-set")
        assert loaded.name == "my-set"
        assert len(loaded.runs) == 1
        assert loaded.runs[0].run_id == "r1"

    def test_load_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_eval_set(tmp_path, "nonexistent")

    def test_roundtrip_preserves_all_fields(self, tmp_path):
        es = EvalSet(name="full-test")
        es.add_run(EvalRunRef(
            run_id="r1",
            timestamp=1234.5,
            artifacts_dir="/tmp/artifacts",
            status="partial",
            total_trials=20,
            success_count=15,
            error_count=3,
            metadata={"env": "docker"},
        ))
        save_eval_set(es, tmp_path)
        loaded = load_eval_set(tmp_path, "full-test")
        r = loaded.runs[0]
        assert r.timestamp == 1234.5
        assert r.status == "partial"
        assert r.metadata["env"] == "docker"
