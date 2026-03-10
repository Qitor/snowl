"""ToolEmu native runtime helpers used by Snowl integrations."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from snowl.errors import SnowlValidationError


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def toolemu_root() -> Path:
    return _project_root() / "references" / "ToolEmu"


def _safe_token(value: str | None, default: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "")).strip("-")
    return token or default


def _ensure_toolemu_importable() -> None:
    root = toolemu_root()
    if not root.exists():
        raise SnowlValidationError(f"ToolEmu reference repo not found: {root}")
    candidates = [root]
    project_root = _project_root()
    for name in ("PromptCoder", "procoder", "Procoder"):
        candidate = project_root / "references" / name
        if candidate.exists():
            candidates.append(candidate)
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)


def _load_openai_llm(
    *,
    model_name: str,
    temperature: float,
    request_timeout: int,
    max_retries: int,
    openai_api_key: str | None = None,
    openai_api_base: str | None = None,
    max_tokens: int | None = None,
    streaming: bool = True,
    callbacks: list[Any] | None = None,
) -> Any:
    _ensure_toolemu_importable()
    try:
        from toolemu.utils import load_openai_llm
    except Exception as exc:
        raise SnowlValidationError(
            "Failed to import ToolEmu runtime dependencies. Install ToolEmu and its Python deps first."
        ) from exc
    return load_openai_llm(
        model_name=model_name,
        temperature=temperature,
        request_timeout=request_timeout,
        max_retries=max_retries,
        openai_api_key=openai_api_key,
        openai_api_base=openai_api_base,
        max_tokens=max_tokens,
        streaming=streaming,
        callbacks=callbacks,
    )


def build_tool_emu_llm(
    role: str,
    *,
    model_name: str | None = None,
    temperature: float | None = None,
    request_timeout: int | None = None,
    max_retries: int | None = None,
    openai_api_key: str | None = None,
    openai_api_base: str | None = None,
    max_tokens: int | None = None,
) -> Any:
    role_upper = role.upper()
    resolved_model_name = model_name or str(os.getenv(f"SNOWL_TOOLEMU_{role_upper}_MODEL", "gpt-4")).strip() or "gpt-4"
    resolved_temperature = (
        float(temperature)
        if temperature is not None
        else float(os.getenv(f"SNOWL_TOOLEMU_{role_upper}_TEMPERATURE", "0.0"))
    )
    resolved_request_timeout = (
        int(request_timeout)
        if request_timeout is not None
        else int(os.getenv(f"SNOWL_TOOLEMU_{role_upper}_TIMEOUT", "300"))
    )
    resolved_max_retries = (
        int(max_retries)
        if max_retries is not None
        else int(os.getenv(f"SNOWL_TOOLEMU_{role_upper}_MAX_RETRIES", "8"))
    )
    resolved_api_key = openai_api_key
    if resolved_api_key is None:
        resolved_api_key = str(
            os.getenv(f"SNOWL_TOOLEMU_{role_upper}_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        ).strip() or None
    resolved_api_base = openai_api_base
    if resolved_api_base is None:
        resolved_api_base = str(
            os.getenv(f"SNOWL_TOOLEMU_{role_upper}_BASE_URL", os.getenv("OPENAI_BASE_URL", ""))
        ).strip() or None
    resolved_max_tokens = max_tokens
    if resolved_max_tokens is None:
        raw = str(os.getenv(f"SNOWL_TOOLEMU_{role_upper}_MAX_TOKENS", "")).strip()
        resolved_max_tokens = int(raw) if raw else None
    return _load_openai_llm(
        model_name=resolved_model_name,
        temperature=resolved_temperature,
        request_timeout=resolved_request_timeout,
        max_retries=resolved_max_retries,
        openai_api_key=resolved_api_key,
        openai_api_base=resolved_api_base,
        max_tokens=resolved_max_tokens,
    )


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


def execute_tool_emu_case(
    case: Mapping[str, Any],
    *,
    agent_llm: Any,
    simulator_llm: Any,
    agent_type: str,
    simulator_type: str,
    max_iterations: int,
    verbose: bool,
) -> tuple[dict[str, Any], str]:
    _ensure_toolemu_importable()
    try:
        from toolemu.agent_executor_builder import build_agent_executor
        from toolemu.utils import (
            case_to_input_dict,
            construct_simple_trajec,
            filter_keys,
            get_toolkit_names,
            replace_agent_action_with_list,
        )
    except Exception as exc:
        raise SnowlValidationError(
            "Failed to import ToolEmu execution modules. Ensure ToolEmu and PromptCoder are installed."
        ) from exc

    executor = build_agent_executor(
        get_toolkit_names(dict(case)),
        agent_llm,
        simulator_llm,
        agent_type=agent_type,
        simulator_type=simulator_type,
        verbose=verbose,
        max_iterations=max_iterations,
    )
    prompt_inputs = filter_keys(case_to_input_dict(dict(case)), list(getattr(executor, "input_keys", ["input"])))
    outputs = executor(prompt_inputs)
    dumped = replace_agent_action_with_list(outputs)
    dumped["case"] = dict(case)
    simple_trajectory = construct_simple_trajec(outputs)
    return dumped, simple_trajectory


def evaluate_tool_emu_trajectory(
    trajectory: Mapping[str, Any],
    *,
    evaluator_llm: Any,
    critique_llm: Any | None = None,
) -> dict[str, float]:
    _ensure_toolemu_importable()
    try:
        from toolemu.evaluators import AgentHelpfulnessEvaluator, AgentRiskyToolCallEvaluator
        from toolemu.utils import convert_to_score
    except Exception as exc:
        raise SnowlValidationError(
            "Failed to import ToolEmu evaluator modules. Ensure ToolEmu and PromptCoder are installed."
        ) from exc

    def _run_eval(factory: Callable[..., Any]) -> float:
        evaluator = factory(evaluator_llm, critique_llm=critique_llm, critique_rounds=0)
        results = evaluator({"trajectory": dict(trajectory)})
        if not results:
            raise SnowlValidationError(f"ToolEmu evaluator returned no results for {factory.__name__}.")
        score_map = dict(results[0].get("eval_scores") or {})
        if factory is AgentRiskyToolCallEvaluator:
            key = "ToolCallRisk"
        else:
            key = "Helpfulness"
        if key not in score_map:
            raise SnowlValidationError(f"ToolEmu evaluator missing metric '{key}'.")
        return float(convert_to_score(score_map[key]))

    return {
        "ToolCallRisk": _run_eval(AgentRiskyToolCallEvaluator),
        "Helpfulness": _run_eval(AgentHelpfulnessEvaluator),
    }
