from __future__ import annotations

import json
import os
from dataclasses import dataclass
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
            '{"thinking":"...","actions":[{"action_type":"CLICK|TYPING|PRESS|SCROLL|WAIT|DONE","parameters":{...}}],"done":false,"done_status":"success|failed|in_progress"}'
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
        usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        latest_observation = ""
        done_status = "in_progress"
        final_score = 0.0

        try:
            if not managed_by_runtime:
                emit({"event": "osworld.container.config", "image": os.getenv("SNOWL_OSWORLD_IMAGE", "happysixd/osworld-docker")})
                emit({"event": "osworld.container.starting"})
                start_evt = env.start_container(image=os.getenv("SNOWL_OSWORLD_IMAGE", "happysixd/osworld-docker"))
                trace_events.append(start_evt)
                emit({"event": "osworld.container.started", "exit_code": start_evt.get("exit_code"), "ready": start_evt.get("ready")})

            for step in range(1, self.max_steps + 1):
                obs = env.observe()
                trace_events.append({"event": "osworld.observe", "status_code": obs.get("status_code")})
                screenshot_bytes = obs.get("screenshot") or b""
                latest_observation = f"screenshot_bytes={len(screenshot_bytes)}"

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
                usage_total["input_tokens"] += response.usage.input_tokens
                usage_total["output_tokens"] += response.usage.output_tokens
                usage_total["total_tokens"] += response.usage.total_tokens

                content = str(response.message.get("content", ""))
                parsed = _extract_json(content)
                if not parsed:
                    trace_events.append({"event": "osworld.parse_error", "step": step, "raw": content})
                    continue

                actions = parsed.get("actions") or []
                for action in actions:
                    if not isinstance(action, dict):
                        continue
                    out = env.execute_action(action)
                    trace_events.append(
                        {
                            "event": "osworld.action",
                            "step": step,
                            "action_type": action.get("action_type"),
                            "status_code": out.get("status_code"),
                            "error": out.get("error"),
                        }
                    )
                    emit(
                        {
                            "event": "osworld.action.executed",
                            "action_type": action.get("action_type"),
                            "status_code": out.get("status_code"),
                            "error": out.get("error"),
                        }
                    )

                done = bool(parsed.get("done", False))
                done_status = str(parsed.get("done_status", "in_progress"))
                if done:
                    break

            eval_out = env.evaluate({"done_status": done_status})
            trace_events.append({"event": "osworld.evaluate", "score": float(eval_out.get("score", 0.0))})
            emit({"event": "osworld.evaluate", "score": float(eval_out.get("score", 0.0))})
            final_score = float(eval_out.get("score", 0.0))
        finally:
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
        }
        state.stop_reason = StopReason.COMPLETED
        return state


@declare_agent()
def agent() -> OSWorldOfficialAgent:
    return OSWorldOfficialAgent()
