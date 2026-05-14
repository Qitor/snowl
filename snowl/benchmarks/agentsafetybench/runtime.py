"""Benchmark-local runtime helper module for `agentsafetybench` integrations.

Framework role:
- Holds benchmark runtime quirks that should not leak into shared eval/runtime code.
- Provides prompt formatting helpers for the LLM judge scorer.

Runtime/usage wiring:
- Referenced by benchmark-specific adapters/scorers or integration glue.
- Key top-level symbols: `agentsafetybench_root`, `resolve_agentsafetybench_output_dir`,
  `persist_agentsafetybench_trajectory`, `persist_agentsafetybench_scores`,
  `format_agentsafetybench_dialog`, `format_agentsafetybench_env_info`.

Change guardrails:
- Must not import from the Agent-SafetyBench Python package.
- Keep benchmark assumptions local unless promoting a shared runtime contract.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from snowl.errors import SnowlValidationError


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def agentsafetybench_root() -> Path:
    return _project_root() / "references" / "Agent-SafetyBench"


def _safe_token(value: str | None, default: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "")).strip("-")
    return token or default


def resolve_agentsafetybench_output_dir(
    project_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
    run_stamp: str | None = None,
) -> Path:
    if output_dir is not None:
        root = Path(output_dir)
    else:
        stamp = str(run_stamp or "").strip() or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
        root = Path(project_dir) / "outputs" / stamp
    root.mkdir(parents=True, exist_ok=True)
    (root / "trajectories").mkdir(parents=True, exist_ok=True)
    (root / "scores").mkdir(parents=True, exist_ok=True)
    return root


def persist_agentsafetybench_trajectory(
    *,
    project_dir: str | Path,
    sample_id: str | None,
    case_id: Any,
    record: Mapping[str, Any],
    output_dir: str | Path | None = None,
    run_stamp: str | None = None,
) -> dict[str, str]:
    out_dir = resolve_agentsafetybench_output_dir(project_dir, output_dir=output_dir, run_stamp=run_stamp)
    token = _safe_token(sample_id or str(case_id), "sample")
    json_path = out_dir / "trajectories" / f"{token}.json"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(dict(record), handle, ensure_ascii=False, indent=2)
    summary_path = out_dir / "trajectories.jsonl"
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"sample_id": sample_id, "case_id": case_id, "path": str(json_path)}, ensure_ascii=False))
        handle.write("\n")
    return {
        "output_dir": str(out_dir),
        "trajectory_json": str(json_path),
        "trajectory_index": str(summary_path),
    }


def persist_agentsafetybench_scores(
    *,
    project_dir: str | Path,
    sample_id: str | None,
    case_id: Any,
    scores: Mapping[str, Any],
    output_dir: str | Path | None = None,
    run_stamp: str | None = None,
) -> dict[str, str]:
    out_dir = resolve_agentsafetybench_output_dir(project_dir, output_dir=output_dir, run_stamp=run_stamp)
    token = _safe_token(sample_id or str(case_id), "sample")
    json_path = out_dir / "scores" / f"{token}.json"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(dict(scores), handle, ensure_ascii=False, indent=2)
    summary_path = out_dir / "scores.jsonl"
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(scores), ensure_ascii=False))
        handle.write("\n")
    return {
        "output_dir": str(out_dir),
        "score_json": str(json_path),
        "score_index": str(summary_path),
    }
