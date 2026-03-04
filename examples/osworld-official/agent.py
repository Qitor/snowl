from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowl.core import AgentContext, AgentState, EnvSpec, StopReason, agent as declare_agent
from snowl.envs import GuiEnv
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig


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
    raw = str(os.getenv("SNOWL_OSWORLD_CAP_ADD", "NET_ADMIN")).strip()
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


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _safe_name(value: str) -> str:
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", value)
    text = re.sub(r"\s+", "_", text).strip("._")
    return text or "unknown"


def _clip_text(value: str, limit: int = 600) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


@dataclass
class OSWorldOfficialAgent:
    agent_id: str = "osworld_official_agent"
    max_steps: int = int(os.getenv("SNOWL_OSWORLD_MAX_STEPS", "15"))
    temperature: float = float(os.getenv("SNOWL_OSWORLD_TEMPERATURE", "0.2"))

    def __post_init__(self) -> None:
        cfg = OpenAICompatibleConfig(
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("OPENAI_API_KEY", "DUMMY_API_KEY_FOR_IMPORT"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            timeout=float(os.getenv("OPENAI_TIMEOUT", "60")),
            max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "2")),
        )
        self._client = OpenAICompatibleChatClient(cfg)
        self._system_prompt = (
            "You are an OSWorld-style GUI agent. "
            "Return ONLY JSON: "
            '{"thinking":"...","actions":[{"action_type":"MOVE_TO|CLICK|RIGHT_CLICK|DOUBLE_CLICK|MOUSE_DOWN|MOUSE_UP|DRAG_TO|SCROLL|TYPING|PRESS|KEY_DOWN|KEY_UP|HOTKEY|WAIT|DONE|FAIL","parameters":{...}}],"done":false,"done_status":"success|failed|in_progress"}'
        )

    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        _ = tools
        event_emitter = context.metadata.get("__snowl_emit_event")
        emit = event_emitter if callable(event_emitter) else (lambda *_args, **_kwargs: None)
        container_session = context.metadata.get("__snowl_container_session")
        sample = dict(context.metadata.get("sample", {}))
        sample_meta = dict(sample.get("metadata", {}))

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
                config={"ready_timeout_sec": float(os.getenv("SNOWL_OSWORLD_READY_TIMEOUT", "240"))},
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
        observe_accessibility = _truthy_env("SNOWL_OSWORLD_OBSERVE_ACCESSIBILITY", default=False)
        observe_terminal = _truthy_env("SNOWL_OSWORLD_OBSERVE_TERMINAL", default=False)
        record_enabled = _truthy_env("SNOWL_OSWORLD_RECORDING", default=True)
        recording_started = False
        run_error: Exception | None = None

        try:
            if not managed_by_runtime:
                emit({"event": "osworld.container.config", "image": os.getenv("SNOWL_OSWORLD_IMAGE", "happysixd/osworld-docker")})
                emit({"event": "osworld.container.starting"})
                start_evt = env.start_container(
                    image=os.getenv("SNOWL_OSWORLD_IMAGE", "happysixd/osworld-docker"),
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

            if self.max_steps <= 0:
                trace_events.append({"event": "osworld.max_steps.zero", "max_steps": self.max_steps})

            for step in range(1, self.max_steps + 1):
                obs = env.observe(
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
                }
                trace_events.append(obs_evt)
                screenshot_bytes = obs.get("screenshot") or b""
                latest_observation = json.dumps(
                    {
                        "screenshot_bytes": len(screenshot_bytes),
                        "accessibility_tree": _clip_text(str(obs.get("accessibility_tree") or ""), limit=1000),
                        "terminal_output": _clip_text(str(obs.get("terminal_output") or ""), limit=500),
                    },
                    ensure_ascii=False,
                )

                prompt = (
                    f"Instruction:\n{sample.get('input', '')}\n\n"
                    f"Task Metadata:\n{json.dumps(sample_meta, ensure_ascii=False)}\n\n"
                    f"Current Observation:\n{latest_observation}\n\n"
                    "Plan the next actions."
                )
                emit(
                    {
                        "event": "runtime.model.query.start",
                        "phase": "agent",
                        "model": getattr(self._client, "model", None),
                    }
                )
                try:
                    response = await self._client.generate(
                        [
                            {"role": "system", "content": self._system_prompt},
                            {"role": "user", "content": prompt},
                        ],
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
                            "messages": [
                                {"role": "system", "content": self._system_prompt},
                                {"role": "user", "content": prompt},
                            ],
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
                parsed = _extract_json(content)
                if not parsed:
                    trace_events.append({"event": "osworld.parse_error", "step": step, "raw": content})
                    continue

                actions = parsed.get("actions") or []
                for action in actions:
                    if isinstance(action, str):
                        action = {"action_type": action, "parameters": {}}
                    if not isinstance(action, dict):
                        trace_events.append({"event": "osworld.action.invalid", "step": step, "raw": str(action)})
                        continue
                    out = env.execute_action(action)
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

                done = bool(parsed.get("done", False))
                done_status = str(parsed.get("done_status", "in_progress"))
                if done:
                    break

            if done_status.lower() in {"failed", "fail"}:
                if not action_history or str((action_history[-1] or {}).get("action_type", "")).upper() != "FAIL":
                    action_history.append({"action_type": "FAIL", "parameters": {}})

            eval_out = env.evaluate(
                {
                    "done_status": done_status,
                    "evaluator": sample_meta.get("evaluator"),
                    "proxy": bool(sample_meta.get("proxy", False)),
                    "sample_id": sample.get("id") or context.sample_id,
                    "task_id": context.task_id,
                    "action_history": action_history,
                }
            )
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
                    rec_dir = Path(os.getenv("SNOWL_OSWORLD_RECORDINGS_DIR", ".snowl/recordings"))
                    sample_token = _safe_name(str(sample.get("id") or context.sample_id or "sample"))
                    rec_name = f"osworld__{sample_token}__{int(time.time() * 1000)}.mp4"
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


@declare_agent()
def agent() -> OSWorldOfficialAgent:
    return OSWorldOfficialAgent()
