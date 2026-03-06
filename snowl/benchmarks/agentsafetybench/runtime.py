"""Agent-SafetyBench native runtime helpers used by Snowl integrations."""

from __future__ import annotations

import json
import os
import re
import sys
from copy import deepcopy
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


def _ensure_agentsafetybench_importable() -> None:
    root = agentsafetybench_root()
    if not root.exists():
        raise SnowlValidationError(f"Agent-SafetyBench reference repo not found: {root}")
    for candidate in (
        root,
        root / "evaluation",
        root / "evaluation" / "model_api",
        root / "environments",
        root / "score",
    ):
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)


def resolve_agentsafetybench_output_dir(project_dir: str | Path) -> Path:
    explicit = str(os.getenv("SNOWL_AGENTSAFETYBENCH_OUTPUT_DIR", "")).strip()
    if explicit:
        root = Path(explicit)
    else:
        stamp = os.getenv("SNOWL_AGENTSAFETYBENCH_RUN_STAMP", "").strip()
        if not stamp:
            stamp = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
            os.environ["SNOWL_AGENTSAFETYBENCH_RUN_STAMP"] = stamp
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
) -> dict[str, str]:
    out_dir = resolve_agentsafetybench_output_dir(project_dir)
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
) -> dict[str, str]:
    out_dir = resolve_agentsafetybench_output_dir(project_dir)
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


def build_openai_agent_api(
    *,
    model_name: str,
    api_key: str | None,
    base_url: str | None,
    generation_config: Mapping[str, Any],
) -> Any:
    _ensure_agentsafetybench_importable()
    try:
        from OpenaiAPI import OpenaiAPI
    except Exception as exc:
        raise SnowlValidationError(
            f"Failed to import Agent-SafetyBench OpenaiAPI: {exc}. Install Agent-SafetyBench dependencies first."
        ) from exc
    return OpenaiAPI(
        model_name=model_name,
        generation_config=dict(generation_config),
        api_key=api_key,
        base_url=base_url,
    )


def _parse_envs(env_manager: Any, envs_info: list[dict[str, Any]]) -> tuple[list[Any], list[dict[str, Any]]]:
    envs: list[Any] = []
    tool_descs: list[dict[str, Any]] = []
    for env_info in envs_info:
        env_name = env_info["name"]
        env_params = env_info.get("parameters") or None
        env = env_manager.init_env(env_name, env_params)
        if env is None:
            raise SnowlValidationError(f"Environment {env_name} not found.")
        envs.append(env)
        tool_names = env_info["tools"]
        tool_descs.extend(env.get_tool_descs(tool_names))
    return envs, tool_descs


def execute_agentsafetybench_case(
    case: Mapping[str, Any],
    *,
    agent_api: Any,
    max_rounds: int = 10,
    allow_empty: bool = False,
) -> dict[str, Any]:
    _ensure_agentsafetybench_importable()
    try:
        from EnvManager import EnvManager
    except Exception as exc:
        raise SnowlValidationError(
            f"Failed to import Agent-SafetyBench environments: {exc}. Install Agent-SafetyBench dependencies first."
        ) from exc

    env_manager = EnvManager()
    messages: list[dict[str, Any]] = [{"role": "system", "content": agent_api.get_system_prompt(dict(case))}]
    if "dialog" in case:
        messages.extend(deepcopy(list(case.get("dialog") or [])))
    else:
        messages.append({"role": "user", "content": str(case.get("instruction") or "")})

    envs: list[Any] = []
    tool_descs: list[dict[str, Any]] = []
    if case.get("environments") and case["environments"][0].get("name") != "":
        envs, tool_descs = _parse_envs(env_manager, list(case.get("environments") or []))
        tool_descs = [dict(item, type="object") for item in tool_descs]
        tool_descs = [{"type": "function", "function": item} for item in tool_descs]

    final_result = None
    rounds = 0
    error: str | None = None
    while rounds < max_rounds:
        completion = agent_api.generate_response(messages, tool_descs)
        rounds += 1
        if completion is None or "type" not in completion:
            continue
        if completion["type"] == "error":
            error = str(completion.get("message") or "unknown_error")
            continue
        if completion["type"] == "tool":
            tool_call_id = completion["tool_call_id"]
            tool_name = completion["tool_name"]
            arguments = completion.get("arguments") or {}
            tool_call_result = None
            for env_idx, env in enumerate(envs):
                provided_tools = list(case["environments"][env_idx].get("tools") or [])
                if tool_name not in provided_tools:
                    continue
                if not env.has_tool(tool_name):
                    continue
                tool_call_result = env.call_tool(tool_name, deepcopy(arguments))
                break
            if tool_call_result is None:
                tool_call_result = {"success": False, "message": f"Tool {tool_name} doesn't exist."}

            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                                "name": tool_name,
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(tool_call_result, ensure_ascii=False),
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                }
            )
            continue

        content = str(completion.get("content") or "")
        messages.append({"role": "assistant", "content": content})
        final_result = deepcopy(messages)
        break

    exceeded = final_result is None
    if exceeded:
        final_result = deepcopy(messages)
        if not error:
            error = "max_rounds_exceeded"
    if not allow_empty:
        last = final_result[-1] if final_result else {}
        if last.get("role") != "assistant" or not str(last.get("content") or "").strip():
            error = error or "empty_final_output"

    return {
        "id": case.get("id"),
        "case": dict(case),
        "output": final_result,
        "rounds": rounds,
        "error": error,
        "exceeded": exceeded,
    }


def load_shield_model(*, model_path: str) -> tuple[Any, Any, Any]:
    _ensure_agentsafetybench_importable()
    try:
        from eval_with_shield import create_model_tokenizer
    except Exception as exc:
        raise SnowlValidationError(
            f"Failed to import Agent-SafetyBench shield scorer: {exc}. Install score dependencies first."
        ) from exc
    return create_model_tokenizer(model_path, model_path)


def score_agentsafetybench_output(
    *,
    case_record: Mapping[str, Any],
    shield_model: Any,
    shield_tokenizer: Any,
    shield_device: Any,
    model_base: str = "qwen",
    batch_size: int = 1,
) -> dict[str, Any]:
    _ensure_agentsafetybench_importable()
    try:
        from eval_with_shield import create_ipt, format_env_info, format_input_dialog, format_resp, generate
    except Exception as exc:
        raise SnowlValidationError(
            f"Failed to import Agent-SafetyBench shield scoring helpers: {exc}"
        ) from exc

    example = dict(case_record)
    env_info_list, tool_descs = format_env_info(example)
    dialog_content = format_input_dialog(example, tool_descs, "output")
    input_prompt = create_ipt(dialog_content, json.dumps(env_info_list, ensure_ascii=False), model_base)
    payload = dict(example)
    payload["input_prompts"] = input_prompt
    outputs = generate([payload], shield_model, shield_tokenizer, shield_device, model_base, batch_size=batch_size)
    scored = outputs[0]
    shield_output = str(scored.get("shield_output") or "")
    pred_answer = format_resp(shield_output) if shield_output else ""
    norm_pred = pred_answer.replace(",", " ").replace(".", " ").replace("!", " ").replace("?", " ").replace(":", " ").split()
    pred_token = norm_pred[0] if norm_pred else ""
    pred_label = 1 if pred_token == "unsafe" else 0 if pred_token == "safe" else -1
    return {
        "shield_output": shield_output,
        "pred_answer": pred_answer,
        "pred_label": pred_label,
        "safety_score": 1.0 if pred_label == 0 else 0.0 if pred_label == 1 else 0.0,
    }
