from __future__ import annotations

import base64
import importlib.util
import hashlib
import json
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from snowl.benchmarks.osworld.evaluator import evaluate_task, run_setup_config
from snowl.agents import build_model_variants
from snowl.core import AgentContext, AgentState, EnvSpec, StopReason, agent as declare_agent
from snowl.envs import GuiEnv
from snowl.model import (
    OpenAICompatibleChatClient,
    OpenAICompatibleConfig,
    ProjectModelEntry,
    ProjectProviderConfig,
)
from snowl.project_config import load_project_config


PROJECT = load_project_config(Path(__file__).parent)
OSWORLD_SETTINGS = PROJECT.benchmark_settings("osworld")


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _resolve_cap_add() -> list[str]:
    raw = str(OSWORLD_SETTINGS.get("cap_add", "NET_ADMIN")).strip()
    if not raw or raw.lower() in {"0", "false", "off", "none"}:
        return []
    caps: list[str] = []
    seen: set[str] = set()
    for token in raw.replace(",", " ").split():
        cap = token.strip()
        if not cap:
            continue
        key = cap.upper()
        if key in seen:
            continue
        seen.add(key)
        caps.append(cap)
    return caps


def _truthy_setting(name: str, default: bool = False) -> bool:
    value = OSWORLD_SETTINGS.get(name, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _safe_name(value: str) -> str:
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", value)
    text = re.sub(r"\s+", "_", text).strip("._")
    return text or "unknown"


def _clip_text(value: str, limit: int = 600) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _resolve_observation_type(model_name: str) -> str:
    env_raw = OSWORLD_SETTINGS.get("observation_type")
    if env_raw is None or not str(env_raw).strip():
        return "screenshot" if _supports_vision(model_name) else "a11y_tree"
    raw = str(env_raw).strip().lower()
    if raw not in {"screenshot", "a11y_tree", "screenshot_a11y_tree"}:
        raise ValueError(
            "osworld.observation_type must be one of: "
            "screenshot, a11y_tree, screenshot_a11y_tree."
        )
    return raw


def _supports_vision(model_name: str) -> bool:
    text = str(model_name or "").strip().lower()
    if not text:
        return False
    signals = (
        "gpt-4o",
        "gpt-4.1",
        "vision",
        "vl",
        "gemini",
        "claude-3",
        "qvq",
    )
    return any(sig in text for sig in signals)


def _build_user_message(
    *,
    observation_type: str,
    observation: dict[str, Any],
) -> tuple[str | list[dict[str, Any]], str, dict[str, Any]]:
    screenshot_bytes = bytes(observation.get("screenshot") or b"")
    accessibility_tree = _clip_text(str(observation.get("accessibility_tree") or ""), limit=4000)
    screenshot_sha256 = hashlib.sha256(screenshot_bytes).hexdigest() if screenshot_bytes else ""

    if observation_type == "a11y_tree":
        observation_text = accessibility_tree
        message_text = (
            "Given the info from accessibility tree as below:\n"
            f"{observation_text}\n"
            "What's the next step that you will do to help with the task?"
        )
        return (
            message_text,
            observation_text,
            {
                "observation_type": "a11y_tree",
                "screenshot_bytes": 0,
                "screenshot_sha256": "",
            },
        )

    if observation_type == "screenshot":
        encoded = base64.b64encode(screenshot_bytes).decode("utf-8")
        observation_text = f"screenshot_bytes={len(screenshot_bytes)}"
        message = [
            {
                "type": "text",
                "text": "Given the screenshot as below. What's the next step that you will do to help with the task?",
            },
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}", "detail": "high"}},
        ]
        return (
            message,
            observation_text,
            {
                "observation_type": "screenshot",
                "screenshot_bytes": len(screenshot_bytes),
                "screenshot_sha256": screenshot_sha256,
            },
        )

    encoded = base64.b64encode(screenshot_bytes).decode("utf-8")
    observation_text = json.dumps(
        {
            "screenshot_bytes": len(screenshot_bytes),
            "accessibility_tree": accessibility_tree,
        },
        ensure_ascii=False,
    )
    message = [
        {
            "type": "text",
            "text": (
                "Given the screenshot and info from accessibility tree as below:\n"
                f"{accessibility_tree}\n"
                "What's the next step that you will do to help with the task?"
            ),
        },
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}", "detail": "high"}},
    ]
    return (
        message,
        observation_text,
        {
            "observation_type": "screenshot_a11y_tree",
            "screenshot_bytes": len(screenshot_bytes),
            "screenshot_sha256": screenshot_sha256,
        },
    )


def _sanitize_messages_for_log(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            items: list[dict[str, Any]] = []
            for item in content:
                if not isinstance(item, dict):
                    items.append({"type": "unknown"})
                    continue
                if item.get("type") == "image_url":
                    items.append({"type": "image_url", "image_url": {"url": "<redacted>"}})
                elif item.get("type") == "text":
                    items.append({"type": "text", "text": _clip_text(str(item.get("text") or ""), limit=1000)})
                else:
                    items.append({"type": str(item.get("type") or "unknown")})
            sanitized.append({"role": msg.get("role"), "content": items})
        else:
            sanitized.append(
                {
                    "role": msg.get("role"),
                    "content": _clip_text(str(content or ""), limit=1500),
                }
            )
    return sanitized


def _ensure_screenshot_for_vlm(
    *,
    env: GuiEnv,
    obs: dict[str, Any],
    include_accessibility: bool,
    include_terminal: bool,
) -> tuple[dict[str, Any], int]:
    if len(bytes(obs.get("screenshot") or b"")) > 0:
        return obs, 0
    retries = max(1, int(OSWORLD_SETTINGS.get("screenshot_retries", 3)))
    wait_sec = max(0.1, float(OSWORLD_SETTINGS.get("screenshot_retry_wait_sec", 1.0)))
    latest = obs
    attempts = 0
    for _ in range(retries):
        attempts += 1
        time.sleep(wait_sec)
        latest = env.observe(
            include_accessibility=include_accessibility,
            include_terminal=include_terminal,
        )
        if len(bytes(latest.get("screenshot") or b"")) > 0:
            break
    return latest, attempts


def _save_observation_frame(
    *,
    sample_id: str,
    variant_id: str,
    step: int,
    screenshot_bytes: bytes,
) -> str | None:
    enabled = _truthy_setting("save_observation_frames", default=True)
    if not enabled or not screenshot_bytes:
        return None
    out_dir = (
        Path(str(OSWORLD_SETTINGS.get("obs_frames_dir", ".snowl/observations")))
        / _safe_name(sample_id or "sample")
        / _safe_name(variant_id or "default")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"step_{int(step):03d}.png"
    path.write_bytes(screenshot_bytes)
    return str(path.resolve())


@lru_cache(maxsize=1)
def _load_osworld_prompts_module():
    prompt_path = Path(__file__).resolve().parents[2] / "references" / "OSWorld" / "mm_agents" / "prompts.py"
    if not prompt_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("osworld_prompts_ref", prompt_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_system_prompt(observation_type: str) -> str:
    key_map = {
        "screenshot": "SYS_PROMPT_IN_SCREENSHOT_OUT_ACTION",
        "a11y_tree": "SYS_PROMPT_IN_A11Y_OUT_ACTION",
        "screenshot_a11y_tree": "SYS_PROMPT_IN_BOTH_OUT_ACTION",
    }
    module = _load_osworld_prompts_module()
    if module is not None:
        key = key_map[observation_type]
        value = getattr(module, key, None)
        if isinstance(value, str) and value.strip():
            return value
    return (
        "You will act as an agent which follow my instruction and perform desktop computer tasks as instructed. "
        "For each step, return one valid action JSON with action_type and parameters, or WAIT/FAIL/DONE."
    )


def _inject_client_password(template: str, client_password: str) -> str:
    # Use literal replacement instead of str.format because official prompts
    # contain many JSON braces that are not format placeholders.
    return str(template or "").replace("{CLIENT_PASSWORD}", str(client_password or ""))


def _extract_actions_and_status(content: str) -> tuple[list[Any], bool | None, str | None]:
    text = str(content or "").strip()
    if not text:
        return [], None, None

    upper = text.upper()
    if upper in {"WAIT", "DONE", "FAIL"}:
        status = "success" if upper == "DONE" else ("failed" if upper == "FAIL" else "in_progress")
        return [{"action_type": upper, "parameters": {}}], upper in {"DONE", "FAIL"}, status

    parsed = _extract_json(text)
    if isinstance(parsed, dict):
        if isinstance(parsed.get("actions"), list):
            done = parsed.get("done")
            done_status = parsed.get("done_status")
            actions = parsed.get("actions") or []
            return list(actions), (bool(done) if isinstance(done, bool) else None), (
                str(done_status) if done_status is not None else None
            )
        if parsed.get("action_type") or parsed.get("action"):
            return [parsed], None, None

    actions: list[Any] = []
    matches = re.findall(r"```json\s+(.*?)\s+```", text, re.DOTALL)
    if not matches:
        matches = re.findall(r"```\s+(.*?)\s+```", text, re.DOTALL)
    for match in matches:
        block = str(match or "").strip()
        if not block:
            continue
        upper_block = block.upper()
        if upper_block in {"WAIT", "DONE", "FAIL"}:
            actions.append({"action_type": upper_block, "parameters": {}})
            continue
        try:
            obj = json.loads(block)
        except Exception:
            continue
        if isinstance(obj, dict):
            actions.append(obj)
        elif isinstance(obj, list):
            actions.extend(obj)
    if actions:
        return actions, None, None
    return [], None, None


@dataclass
class OSWorldOfficialAgent:
    model_config: OpenAICompatibleConfig
    agent_id: str = "osworld_official_agent"
    max_steps: int = int(OSWORLD_SETTINGS.get("max_steps", 15))
    temperature: float = float(OSWORLD_SETTINGS.get("temperature", 0.2))

    def __post_init__(self) -> None:
        self._client = OpenAICompatibleChatClient(self.model_config)
        self._client_password = str(OSWORLD_SETTINGS.get("client_password", "password"))

    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        _ = tools
        event_emitter = context.metadata.get("__snowl_emit_event")
        emit = event_emitter if callable(event_emitter) else (lambda *_args, **_kwargs: None)
        container_session = context.metadata.get("__snowl_container_session")
        sample = dict(context.metadata.get("sample", {}))
        sample_meta = dict(sample.get("metadata", {}))
        variant_id = str(context.metadata.get("variant_id") or "default")

        managed_env = (
            getattr(container_session, "env", None)
            if getattr(container_session, "kind", "") == "gui_container"
            else None
        )
        env = (
            managed_env
            if managed_env is not None
            else GuiEnv(
                env_spec=EnvSpec(
                    env_type="gui",
                    provided_ops=(
                        "gui.action",
                        "gui.click",
                        "gui.type",
                        "gui.key",
                        "gui.scroll",
                        "gui.observe",
                        "gui.wait",
                        "gui.terminate",
                    ),
                ),
                config={"ready_timeout_sec": float(OSWORLD_SETTINGS.get("ready_timeout", 240))},
            )
        )
        managed_by_runtime = managed_env is not None

        trace_events: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        latest_observation = ""
        done_status = "in_progress"
        final_score = 0.0
        action_history: list[Any] = []
        observation_type = _resolve_observation_type(self.model_config.model)
        system_prompt_base = _inject_client_password(
            _resolve_system_prompt(observation_type),
            self._client_password,
        )
        max_trajectory_length = max(0, int(OSWORLD_SETTINGS.get("max_trajectory_length", 3)))
        prompt_user_history: list[str | list[dict[str, Any]]] = []
        prompt_assistant_history: list[str] = []
        observe_accessibility = observation_type in {"a11y_tree", "screenshot_a11y_tree"}
        observe_terminal = False
        record_enabled = _truthy_setting("recording", default=True)
        recording_started = False
        run_error: Exception | None = None

        try:
            if not managed_by_runtime:
                emit({"event": "osworld.container.config", "image": str(OSWORLD_SETTINGS.get("image", "happysixd/osworld-docker"))})
                emit({"event": "osworld.container.starting"})
                start_evt = env.start_container(
                    image=str(OSWORLD_SETTINGS.get("image", "happysixd/osworld-docker")),
                    cap_add=_resolve_cap_add(),
                )
                trace_events.append(start_evt)
                emit({"event": "osworld.container.started", "exit_code": start_evt.get("exit_code"), "ready": start_evt.get("ready")})

            if record_enabled:
                rec_start = env.start_recording()
                trace_events.append(
                    {
                        "event": "osworld.recording.start",
                        "ok": bool(rec_start.get("ok")),
                        "status_code": rec_start.get("status_code"),
                        "error": rec_start.get("error"),
                    }
                )
                recording_started = bool(rec_start.get("ok"))
                emit(
                    {
                        "event": "osworld.recording.start",
                        "ok": recording_started,
                        "status_code": rec_start.get("status_code"),
                    }
                )

            setup_cfg = sample_meta.get("config") or []
            if isinstance(setup_cfg, Sequence) and not isinstance(setup_cfg, (str, bytes)) and setup_cfg:
                endpoint = str(env.config.get("controller_endpoint") or env.controller_endpoint or "")
                if not endpoint:
                    raise RuntimeError("Missing controller endpoint before OSWorld setup.")
                setup_events = run_setup_config(endpoint=endpoint, setup_config=list(setup_cfg))
                setup_failed = any(not bool(evt.get("ok", False)) for evt in setup_events)
                trace_events.append(
                    {
                        "event": "osworld.setup",
                        "steps": len(setup_events),
                        "failed": setup_failed,
                        "results": setup_events,
                    }
                )
                emit({"event": "osworld.setup", "steps": len(setup_events), "failed": setup_failed})
                if setup_failed:
                    first_error = next((evt for evt in setup_events if not bool(evt.get("ok", False))), {})
                    raise RuntimeError(f"osworld setup failed: {first_error}")

            if self.max_steps <= 0:
                trace_events.append({"event": "osworld.max_steps.zero", "max_steps": self.max_steps})

            for step in range(1, self.max_steps + 1):
                obs = env.observe(
                    include_accessibility=observe_accessibility,
                    include_terminal=observe_terminal,
                )
                screenshot_retry_attempts = 0
                if observation_type in {"screenshot", "screenshot_a11y_tree"}:
                    obs, screenshot_retry_attempts = _ensure_screenshot_for_vlm(
                        env=env,
                        obs=obs,
                        include_accessibility=observe_accessibility,
                        include_terminal=observe_terminal,
                    )
                obs_evt = {
                    "event": "osworld.observe",
                    "step": step,
                    "status_code": obs.get("status_code"),
                    "screenshot_bytes": len(obs.get("screenshot") or b""),
                    "accessibility_chars": len(str(obs.get("accessibility_tree") or "")),
                    "terminal_chars": len(str(obs.get("terminal_output") or "")),
                    "screenshot_retry_attempts": screenshot_retry_attempts,
                }
                trace_events.append(obs_evt)
                if observation_type in {"screenshot", "screenshot_a11y_tree"} and not _supports_vision(
                    getattr(self._client, "model", "")
                ):
                    raise RuntimeError(
                        "Observation type requires screenshot, but current model is not a VLM. "
                        "Set osworld.observation_type=a11y_tree or switch to a vision model."
                    )
                screenshot_bytes = bytes(obs.get("screenshot") or b"")
                saved_frame_path = _save_observation_frame(
                    sample_id=str(sample.get("id") or context.sample_id or ""),
                    variant_id=variant_id,
                    step=step,
                    screenshot_bytes=screenshot_bytes,
                )
                user_content, latest_observation, observation_meta = _build_user_message(
                    observation_type=observation_type,
                    observation=obs,
                )
                if saved_frame_path:
                    observation_meta["saved_frame"] = saved_frame_path
                instruction = str(sample.get("input", ""))
                system_message = system_prompt_base + "\nYou are asked to complete the following task: " + instruction
                request_messages: list[dict[str, Any]] = [{"role": "system", "content": system_message}]
                if max_trajectory_length > 0:
                    hist_users = prompt_user_history[-max_trajectory_length:]
                    hist_assistants = prompt_assistant_history[-max_trajectory_length:]
                else:
                    hist_users = []
                    hist_assistants = []
                for hist_user, hist_assistant in zip(hist_users, hist_assistants):
                    request_messages.append({"role": "user", "content": hist_user})
                    request_messages.append({"role": "assistant", "content": hist_assistant or "No valid action"})
                request_messages.append({"role": "user", "content": user_content})
                emit(
                    {
                        "event": "runtime.model.query.start",
                        "phase": "agent",
                        "model": getattr(self._client, "model", None),
                    }
                )
                try:
                    response = await self._client.generate(
                        request_messages,
                        temperature=self.temperature,
                    )
                except Exception as exc:
                    emit(
                        {
                            "event": "runtime.model.query.error",
                            "phase": "error",
                            "model": getattr(self._client, "model", None),
                            "message": str(exc),
                        }
                    )
                    raise
                emit(
                    {
                        "event": "runtime.model.query.finish",
                        "phase": "agent",
                        "model": getattr(self._client, "model", None),
                        "input_tokens": int(getattr(response.usage, "input_tokens", 0)),
                        "output_tokens": int(getattr(response.usage, "output_tokens", 0)),
                        "total_tokens": int(getattr(response.usage, "total_tokens", 0)),
                    }
                )
                emit(
                    {
                        "event": "runtime.model.io",
                        "phase": "agent",
                        "model": getattr(self._client, "model", None),
                        "step": step,
                        "message": "full model request/response captured",
                        "request": {
                            "messages": _sanitize_messages_for_log(request_messages),
                            "observation_meta": observation_meta,
                            "generation_kwargs": {"temperature": self.temperature},
                        },
                        "response": {
                            "message": dict(response.message),
                            "raw": dict(response.raw),
                            "usage": {
                                "input_tokens": int(getattr(response.usage, "input_tokens", 0)),
                                "output_tokens": int(getattr(response.usage, "output_tokens", 0)),
                                "total_tokens": int(getattr(response.usage, "total_tokens", 0)),
                            },
                        },
                    }
                )
                usage_total["input_tokens"] += int(getattr(response.usage, "input_tokens", 0))
                usage_total["output_tokens"] += int(getattr(response.usage, "output_tokens", 0))
                usage_total["total_tokens"] += int(getattr(response.usage, "total_tokens", 0))

                content = str(response.message.get("content", ""))
                prompt_user_history.append(user_content)
                prompt_assistant_history.append(content)
                actions, parsed_done, parsed_done_status = _extract_actions_and_status(content)
                if not actions:
                    trace_events.append({"event": "osworld.parse_error", "step": step, "raw": content})
                    continue

                for action in actions:
                    if isinstance(action, str):
                        action = {"action_type": str(action).upper(), "parameters": {}}
                    if not isinstance(action, dict):
                        trace_events.append({"event": "osworld.action.invalid", "step": step, "raw": str(action)})
                        continue
                    if "parameters" not in action:
                        params = {
                            k: v
                            for k, v in action.items()
                            if k
                            not in {
                                "action_type",
                                "action",
                            }
                        }
                        action = {
                            "action_type": str(action.get("action_type") or action.get("action") or ""),
                            "parameters": params,
                        }
                    action_type = str(action.get("action_type") or "").upper()
                    if action_type in {"DONE", "FAIL"}:
                        action_history.append({"action_type": action_type, "parameters": {}})
                        trace_events.append(
                            {
                                "event": "osworld.action",
                                "step": step,
                                "action": dict(action),
                                "action_type": action_type,
                                "status_code": None,
                                "error": None,
                                "body": "",
                                "payload": None,
                            }
                        )
                        emit(
                            {
                                "event": "osworld.action.executed",
                                "step": step,
                                "action_type": action_type,
                                "status_code": None,
                                "error": None,
                            }
                        )
                        continue
                    try:
                        out = env.execute_action(action)
                    except Exception as exc:
                        out = {
                            "event": "gui.action_error",
                            "status_code": 400,
                            "error": str(exc),
                            "payload": None,
                        }
                    action_history.append(dict(action))
                    trace_events.append(
                        {
                            "event": "osworld.action",
                            "step": step,
                            "action": dict(action),
                            "action_type": action.get("action_type"),
                            "status_code": out.get("status_code"),
                            "error": out.get("error"),
                            "body": _clip_text(str(out.get("body") or ""), limit=1200),
                            "payload": out.get("payload"),
                        }
                    )
                    emit(
                        {
                            "event": "osworld.action.executed",
                            "step": step,
                            "action_type": action.get("action_type"),
                            "status_code": out.get("status_code"),
                            "error": out.get("error"),
                        }
                    )

                if parsed_done is not None:
                    done = bool(parsed_done)
                else:
                    done = any(
                        str((x or {}).get("action_type", "")).upper() in {"DONE", "FAIL"}
                        for x in actions
                        if isinstance(x, dict)
                    )
                if parsed_done_status is not None:
                    done_status = str(parsed_done_status)
                elif any(str((x or {}).get("action_type", "")).upper() == "DONE" for x in actions if isinstance(x, dict)):
                    done_status = "success"
                elif any(str((x or {}).get("action_type", "")).upper() == "FAIL" for x in actions if isinstance(x, dict)):
                    done_status = "failed"
                else:
                    done_status = "in_progress"
                if done:
                    break

            if done_status.lower() in {"failed", "fail"}:
                if not action_history or str((action_history[-1] or {}).get("action_type", "")).upper() != "FAIL":
                    action_history.append({"action_type": "FAIL", "parameters": {}})

            evaluator_cfg = sample_meta.get("evaluator")
            if isinstance(evaluator_cfg, dict):
                endpoint = str(env.config.get("controller_endpoint") or env.controller_endpoint or "")
                try:
                    eval_out = evaluate_task(
                        endpoint=endpoint,
                        evaluator=evaluator_cfg,
                        action_history=action_history,
                        proxy=bool(sample_meta.get("proxy", False)),
                        sample_id=str(sample.get("id") or context.sample_id or ""),
                        task_id=str(context.task_id or ""),
                    )
                except Exception as exc:
                    eval_out = {
                        "event": "gui.evaluate",
                        "score": 0.0,
                        "simulated": True,
                        "error": str(exc),
                        "mode": "osworld_evaluator_fallback",
                    }
            else:
                eval_out = env.evaluate({"done_status": done_status})

            trace_events.append(
                {
                    "event": "osworld.evaluate",
                    "score": float(eval_out.get("score", 0.0)),
                    "simulated": bool(eval_out.get("simulated", False)),
                    "error": eval_out.get("error"),
                    "mode": eval_out.get("mode"),
                    "metric": eval_out.get("metric"),
                    "metrics": eval_out.get("metrics"),
                    "postconfig": eval_out.get("postconfig"),
                }
            )
            emit(
                {
                    "event": "osworld.evaluate",
                    "score": float(eval_out.get("score", 0.0)),
                    "simulated": bool(eval_out.get("simulated", False)),
                    "error": eval_out.get("error"),
                    "mode": eval_out.get("mode"),
                }
            )
            final_score = float(eval_out.get("score", 0.0))
        except Exception as exc:
            run_error = exc
            trace_events.append({"event": "osworld.agent.error", "message": str(exc)})
        finally:
            if recording_started:
                rec_stop = env.end_recording()
                rec_bytes = bytes(rec_stop.get("recording_bytes") or b"")
                if rec_bytes:
                    rec_dir = Path(str(OSWORLD_SETTINGS.get("recordings_dir", ".snowl/recordings")))
                    sample_token = _safe_name(str(sample.get("id") or context.sample_id or "sample"))
                    variant_token = _safe_name(variant_id)
                    rec_name = f"osworld__{sample_token}__{variant_token}__{int(time.time() * 1000)}.mp4"
                    rec_path = rec_dir / rec_name
                    rec_path.parent.mkdir(parents=True, exist_ok=True)
                    rec_path.write_bytes(rec_bytes)
                    artifacts.append(
                        {
                            "name": "recording_mp4",
                            "uri": str(rec_path.resolve()),
                            "media_type": "video/mp4",
                        }
                    )
                    trace_events.append(
                        {
                            "event": "osworld.recording.saved",
                            "path": str(rec_path.resolve()),
                            "bytes": len(rec_bytes),
                        }
                    )
                    emit(
                        {
                            "event": "osworld.recording.saved",
                            "path": str(rec_path.resolve()),
                            "bytes": len(rec_bytes),
                        }
                    )
                else:
                    trace_events.append(
                        {
                            "event": "osworld.recording.stop",
                            "ok": bool(rec_stop.get("ok")),
                            "status_code": rec_stop.get("status_code"),
                            "error": rec_stop.get("error"),
                            "bytes": int(rec_stop.get("bytes") or 0),
                        }
                    )
            if not managed_by_runtime:
                emit({"event": "osworld.container.stopping"})
                stop_evt = env.stop_container()
                trace_events.append(stop_evt)
                emit({"event": "osworld.container.stopped", "exit_code": stop_evt.get("exit_code")})

            state.output = {
                "message": {"role": "assistant", "content": latest_observation},
                "usage": usage_total,
                "trace_events": trace_events,
                "osworld_score": final_score,
                "artifacts": artifacts,
            }
            state.stop_reason = StopReason.ERROR if run_error is not None else StopReason.COMPLETED
        if run_error is not None:
            raise run_error
        return state


def _build_osworld_agent(
    model_entry: ProjectModelEntry,
    provider: ProjectProviderConfig,
) -> OSWorldOfficialAgent:
    _ = provider
    return OSWorldOfficialAgent(model_config=model_entry.config)


@declare_agent(agent_id="osworld_official_agent")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="osworld_official_agent",
        factory=_build_osworld_agent,
    )
