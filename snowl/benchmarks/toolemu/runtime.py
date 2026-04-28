"""Benchmark-local runtime helper module for `toolemu` integrations.

Framework role:
- Holds benchmark runtime quirks that should not leak into shared eval/runtime code.

Runtime/usage wiring:
- Referenced by benchmark-specific adapters/scorers or integration glue.
- Key top-level symbols in this file: `_project_root`, `toolemu_root`, `_safe_token`, `_ensure_toolemu_importable`, `_load_openai_llm`, `build_tool_emu_llm`.

Change guardrails:
- Keep benchmark assumptions local unless promoting a shared runtime contract.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _safe_token(value: str | None, default: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "")).strip("-")
    return token or default


def resolve_toolemu_output_dir(
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


def persist_tool_emu_trajectory(
    *,
    project_dir: str | Path,
    sample_id: str | None,
    case_name: str | None,
    trajectory: Mapping[str, Any],
    simple_trajectory: str,
    extra: Mapping[str, Any] | None = None,
    output_dir: str | Path | None = None,
    run_stamp: str | None = None,
) -> dict[str, str]:
    out_dir = resolve_toolemu_output_dir(project_dir, output_dir=output_dir, run_stamp=run_stamp)
    token = _safe_token(sample_id or case_name, "sample")
    payload = dict(trajectory)
    if extra:
        payload.update(dict(extra))

    json_path = out_dir / "trajectories" / f"{token}.json"
    txt_path = out_dir / "trajectories" / f"{token}_simplified.txt"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    txt_path.write_text(simple_trajectory, encoding="utf-8")

    summary_path = out_dir / "trajectories.jsonl"
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"sample_id": sample_id, "case_name": case_name, "path": str(json_path)}, ensure_ascii=False))
        handle.write("\n")

    return {
        "output_dir": str(out_dir),
        "trajectory_json": str(json_path),
        "trajectory_text": str(txt_path),
        "trajectory_index": str(summary_path),
    }


def persist_tool_emu_scores(
    *,
    project_dir: str | Path,
    sample_id: str | None,
    case_name: str | None,
    scores: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
    output_dir: str | Path | None = None,
    run_stamp: str | None = None,
) -> dict[str, str]:
    out_dir = resolve_toolemu_output_dir(project_dir, output_dir=output_dir, run_stamp=run_stamp)
    token = _safe_token(sample_id or case_name, "sample")
    payload: dict[str, Any] = {
        "sample_id": sample_id,
        "case_name": case_name,
        "scores": dict(scores),
    }
    if extra:
        payload.update(dict(extra))

    json_path = out_dir / "scores" / f"{token}.json"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    summary_path = out_dir / "scores.jsonl"
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")

    return {
        "output_dir": str(out_dir),
        "score_json": str(json_path),
        "score_index": str(summary_path),
    }
