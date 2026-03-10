from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from snowl.agents import build_model_variants
from snowl.core import AgentContext, AgentState, EnvSpec, StopReason, agent as declare_agent
from snowl.envs import TerminalEnv
from snowl.model import (
    OpenAICompatibleChatClient,
    OpenAICompatibleConfig,
    ProjectModelEntry,
    ProjectProviderConfig,
)
from snowl.project_config import load_project_config


ROOT = Path(__file__).resolve().parents[2]
PROJECT = load_project_config(Path(__file__).parent)
TB_SETTINGS = PROJECT.benchmark_settings("terminalbench")
TERMINUS_PROMPT_PATH = (
    ROOT
    / "references"
    / "terminal-bench"
    / "terminal_bench"
    / "agents"
    / "prompt-templates"
    / "terminus.txt"
)
TIMEOUT_PROMPT_PATH = (
    ROOT
    / "references"
    / "terminal-bench"
    / "terminal_bench"
    / "agents"
    / "prompt-templates"
    / "timeout.txt"
)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _parse_pytest_results(content: str) -> dict[str, str]:
    import re

    parts = re.split(r"=+\s*short test summary info\s*=+", content, flags=re.IGNORECASE, maxsplit=1)
    if len(parts) < 2:
        return {}
    out: dict[str, str] = {}
    for raw_line in parts[1].splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("failed"):
            chunks = line.split(" - ")
            if len(chunks) > 1:
                line = " - ".join(chunks[:-1])
        tokens = line.split(maxsplit=1)
        if len(tokens) < 2:
            continue
        status = tokens[0].strip().strip(":").lower()
        test_name = tokens[1].strip().split("::", maxsplit=1)[-1]
        if not test_name:
            continue
        out[test_name] = "passed" if status in {"passed", "skipped", "xfail"} else "failed"
    return out

def _tail(text: Any, limit: int = 240) -> str:
    raw = str(text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[-limit:]


@dataclass
class TerminusOfficialAgent:
    model_config: OpenAICompatibleConfig
    agent_id: str = "terminalbench_official_agent"
    max_episodes: int = int(TB_SETTINGS.get("max_episodes", 8))
    max_parse_retries: int = int(TB_SETTINGS.get("max_parse_retries", 3))
    temperature: float = float(TB_SETTINGS.get("temperature", 0.2))

    def __post_init__(self) -> None:
        self._client: OpenAICompatibleChatClient | None = None
        self._response_schema = json.dumps(
            {
                "type": "object",
                "properties": {
                    "state_analysis": {"type": "string"},
                    "explanation": {"type": "string"},
                    "commands": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "keystrokes": {"type": "string"},
                                "is_blocking": {"type": "boolean"},
                                "timeout_sec": {"type": "number"},
                            },
                            "required": ["keystrokes", "is_blocking", "timeout_sec"],
                            "additionalProperties": False,
                        },
                    },
                    "is_task_complete": {"type": "boolean"},
                },
                "required": ["state_analysis", "explanation", "commands", "is_task_complete"],
                "additionalProperties": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        self._prompt_template = TERMINUS_PROMPT_PATH.read_text(encoding="utf-8")
        self._timeout_template = TIMEOUT_PROMPT_PATH.read_text(encoding="utf-8")

    def _ensure_client(self) -> OpenAICompatibleChatClient:
        if self._client is not None:
            return self._client
        self._client = OpenAICompatibleChatClient(self.model_config)
        return self._client

    def _should_block_tmux_command(self, keystrokes: str, is_blocking: bool) -> bool:
        stripped = keystrokes.strip()
        return is_blocking and not (stripped.endswith("EOF") or stripped.endswith("&"))

    def _normalize_keystrokes(self, keystrokes: str, *, is_blocking: bool) -> str:
        text = str(keystrokes or "")
        if is_blocking and text and not text.endswith("\n"):
            return text + "\n"
        return text

    def _build_env(self, context: AgentContext) -> TerminalEnv:
        sample = dict(context.metadata.get("sample", {}))
        sample_meta = dict(sample.get("metadata", {}))
        task_id = str(sample_meta.get("task_id") or "task")
        sample_id = str(sample.get("id") or "sample")
        variant_id = str(context.metadata.get("variant_id") or "default")
        safe_task = re.sub(r"[^a-zA-Z0-9._-]+", "-", task_id).strip("-") or "task"
        safe_sample = re.sub(r"[^a-zA-Z0-9._-]+", "-", sample_id).strip("-") or "sample"
        safe_variant = re.sub(r"[^a-zA-Z0-9._-]+", "-", variant_id).strip("-") or "default"
        trial_name = f"snowl-tb-{safe_task}-{safe_sample[:12]}-{safe_variant[:12]}"
        workdir = sample_meta.get("task_root") or str(ROOT)
        workdir_path = Path(str(workdir)).resolve()
        logs_root = workdir_path / ".snowl_logs" / safe_sample / safe_variant
        agent_logs_root = workdir_path / ".snowl_agent_logs" / safe_sample / safe_variant
        logs_root.mkdir(parents=True, exist_ok=True)
        agent_logs_root.mkdir(parents=True, exist_ok=True)
        docker_compose_path = str(sample_meta.get("docker_compose_path") or "").strip()
        use_compose = bool(docker_compose_path and Path(docker_compose_path).exists())
        compose_build = bool(TB_SETTINGS.get("compose_build", True))
        compose_env = {
            "T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME": trial_name,
            "T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME": f"tb__{safe_task}__{safe_variant}__client",
            "T_BENCH_TASK_DOCKER_NAME_PREFIX": f"tb__{safe_task}__{safe_variant}",
            "T_BENCH_CONTAINER_LOGS_PATH": "/var/log/tbench",
            "T_BENCH_CONTAINER_AGENT_LOGS_PATH": "/agent-logs",
            "T_BENCH_TEST_DIR": "/tests",
            "T_BENCH_TASK_LOGS_PATH": str(logs_root),
            "T_BENCH_TASK_AGENT_LOGS_PATH": str(agent_logs_root),
            "TEST_DIR": "/tests",
        }
        return TerminalEnv(
            env_spec=EnvSpec(
                env_type="terminal",
                provided_ops=(
                    "process.run",
                    "terminal.exec",
                    "terminal.send_keys",
                    "terminal.capture",
                    "terminal.wait",
                ),
            ),
            workdir=workdir,
            compose_file=(docker_compose_path if docker_compose_path else None),
            use_docker_compose=use_compose,
            compose_build=compose_build,
            compose_project=trial_name,
            compose_service=str(sample_meta.get("compose_service", "client")),
            compose_env=compose_env,
        )

    async def _llm_query_handler(
        self,
        *,
        client: OpenAICompatibleChatClient,
        prompt: str,
        traj: list[dict[str, str]],
        emit,
        trace_events: list[dict[str, Any]],
        usage_total: dict[str, int],
        episode: int,
    ) -> dict[str, Any]:
        traj.append({"role": "user", "content": prompt})
        for parse_attempt in range(1, self.max_parse_retries + 1):
            emit(
                {
                    "event": "runtime.model.query.start",
                    "phase": "agent",
                    "model": getattr(client, "model", None),
                    "episode": episode,
                    "parse_attempt": parse_attempt,
                }
            )
            try:
                resp = await client.generate(
                    list(traj),
                    temperature=self.temperature,
                )
            except Exception as exc:
                emit(
                    {
                        "event": "runtime.model.query.error",
                        "phase": "error",
                        "model": getattr(client, "model", None),
                        "message": str(exc),
                        "episode": episode,
                        "parse_attempt": parse_attempt,
                    }
                )
                raise
            emit(
                {
                    "event": "runtime.model.query.finish",
                    "phase": "agent",
                    "model": getattr(client, "model", None),
                    "input_tokens": int(getattr(resp.usage, "input_tokens", 0)),
                    "output_tokens": int(getattr(resp.usage, "output_tokens", 0)),
                    "total_tokens": int(getattr(resp.usage, "total_tokens", 0)),
                    "episode": episode,
                    "parse_attempt": parse_attempt,
                }
            )
            usage_total["input_tokens"] += resp.usage.input_tokens
            usage_total["output_tokens"] += resp.usage.output_tokens
            usage_total["total_tokens"] += resp.usage.total_tokens

            content = str(resp.message.get("content", ""))
            traj.append({"role": "assistant", "content": content})
            parsed = _extract_json_object(content)
            if parsed is not None:
                return parsed
            trace_events.append(
                {
                    "event": "terminalbench.parse_error",
                    "episode": episode,
                    "parse_attempt": parse_attempt,
                    "max_parse_retries": self.max_parse_retries,
                    "raw": content,
                }
            )

        raise RuntimeError(
            "terminalbench model response parse failed after "
            f"{self.max_parse_retries} attempts in episode {episode}"
        )

    async def run(
        self,
        state: AgentState,
        context: AgentContext,
        tools=None,
    ) -> AgentState:
        _ = tools
        event_emitter = context.metadata.get("__snowl_emit_event")
        emit = event_emitter if callable(event_emitter) else (lambda *_args, **_kwargs: None)
        container_session = context.metadata.get("__snowl_container_session")
        client = self._ensure_client()
        managed_env = (
            getattr(container_session, "env", None)
            if getattr(container_session, "kind", "") == "terminal_compose"
            else None
        )
        env = managed_env if managed_env is not None else self._build_env(context)
        managed_by_runtime = managed_env is not None
        sample = dict(context.metadata.get("sample", {}))
        meta = dict(sample.get("metadata", {}))
        instruction = str(sample.get("input") or "")
        trace_events: list[dict[str, Any]] = []
        traj: list[dict[str, str]] = []
        usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        terminal_state = env.capture()
        test_output = terminal_state

        def emit_cmd(event_name: str, out: Mapping[str, Any] | None = None, **extra: Any) -> None:
            payload = {
                "event": event_name,
                "phase": "env",
                **extra,
            }
            if out is not None:
                cmd = out.get("command")
                payload.update(
                    {
                        "exit_code": out.get("exit_code"),
                        "duration_ms": out.get("duration_ms"),
                        "command_text": out.get("command_text") or (" ".join(cmd) if isinstance(cmd, list) else cmd),
                        "stdout_tail": _tail(out.get("stdout")),
                        "stderr_tail": _tail(out.get("stderr")),
                    }
                )
            emit(payload)

        def emit_env_stream(evt: Mapping[str, Any]) -> None:
            payload = dict(evt or {})
            payload.setdefault("phase", "env")
            payload.setdefault("project", env.compose_project)
            payload.setdefault("compose_file", env.compose_file)
            emit(payload)

        try:
            if env.use_docker_compose and not managed_by_runtime:
                emit(
                    {
                        "event": "terminalbench.container.config",
                        "compose_file": env.compose_file,
                        "project": env.compose_project,
                        "service": env.compose_service,
                        "compose_build": env.compose_build,
                        "env_injected": {
                            "client_container": env.compose_env.get("T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME"),
                            "client_image": env.compose_env.get("T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME"),
                            "test_dir": env.compose_env.get("T_BENCH_TEST_DIR"),
                            "task_logs": env.compose_env.get("T_BENCH_TASK_LOGS_PATH"),
                            "agent_logs": env.compose_env.get("T_BENCH_TASK_AGENT_LOGS_PATH"),
                        },
                    }
                )
                emit_cmd("terminalbench.container.starting", None, compose_file=env.compose_file, project=env.compose_project)
                up_out = env.compose_up(on_event=emit_env_stream)
                trace_events.append(up_out)
                build_out = up_out.get("build")
                if isinstance(build_out, Mapping):
                    emit_cmd("terminalbench.container.build", build_out, project=env.compose_project)
                emit_cmd("terminalbench.container.started", up_out, project=env.compose_project)
                if up_out.get("exit_code", 1) != 0:
                    raise RuntimeError(
                        "terminalbench docker compose up failed: "
                        + str((up_out.get("stderr") or up_out.get("stdout") or "").strip())
                    )
            elif not env.use_docker_compose:
                emit(
                    {
                        "event": "terminalbench.container.disabled",
                        "reason": "compose_file_not_found",
                        "task_id": str(meta.get("task_id") or ""),
                        "docker_compose_path": str(meta.get("docker_compose_path") or ""),
                    }
                )

            for episode in range(1, self.max_episodes + 1):
                prompt = (
                    self._prompt_template.format(
                        response_schema=self._response_schema,
                        instruction=instruction,
                        history="",
                        terminal_state=terminal_state,
                    )
                    if episode == 1
                    else terminal_state
                )
                parsed = await self._llm_query_handler(
                    client=client,
                    prompt=prompt,
                    traj=traj,
                    emit=emit,
                    trace_events=trace_events,
                    usage_total=usage_total,
                    episode=episode,
                )

                commands = parsed.get("commands") or []
                timeout_happened = False
                timeout_message = ""
                for cmd in commands:
                    if not isinstance(cmd, Mapping):
                        continue
                    raw_keystrokes = str(cmd.get("keystrokes", ""))
                    requested_blocking = bool(cmd.get("is_blocking", False))
                    is_blocking = self._should_block_tmux_command(
                        raw_keystrokes,
                        requested_blocking,
                    )
                    keystrokes = self._normalize_keystrokes(raw_keystrokes, is_blocking=is_blocking)
                    timeout_sec = float(cmd.get("timeout_sec", 180.0))
                    try:
                        out = env.send_keys(
                            keystrokes=keystrokes,
                            is_blocking=is_blocking,
                            timeout_sec=timeout_sec,
                        )
                        trace_events.append(
                            {
                                "event": "terminalbench.command",
                                "episode": episode,
                                "keystrokes": keystrokes,
                                "is_blocking": is_blocking,
                                "requested_blocking": requested_blocking,
                                "timeout_sec": timeout_sec,
                                "exit_code": out.get("exit_code"),
                            }
                        )
                        emit_cmd(
                            "terminalbench.command.exec",
                            out,
                            episode=episode,
                            keystrokes=keystrokes,
                            is_blocking=is_blocking,
                            requested_blocking=requested_blocking,
                            timeout_sec=timeout_sec,
                        )
                    except Exception as exc:
                        timeout_happened = True
                        timeout_message = self._timeout_template.format(
                            timeout_sec=timeout_sec,
                            command=keystrokes,
                            terminal_state=env.capture(),
                        )
                        trace_events.append(
                            {
                                "event": "terminalbench.command_timeout",
                                "episode": episode,
                                "keystrokes": keystrokes,
                                "error": str(exc),
                            }
                        )
                        break

                if timeout_happened:
                    terminal_state = timeout_message
                else:
                    terminal_state = env.capture()
                if bool(parsed.get("is_task_complete", False)):
                    break

            parser_results: dict[str, str] = {}
            run_tests_path = Path(str(meta.get("run_tests_path", "")))
            if run_tests_path.exists() and bool(TB_SETTINGS.get("run_tests", False)):
                try:
                    emit(
                        {
                            "event": "terminalbench.run_tests.start",
                            "run_tests_path": str(run_tests_path),
                            "timeout_seconds": float(meta.get("max_test_timeout_sec") or 180.0),
                        }
                    )
                    result = env.run_tests(
                        run_tests_path=str(run_tests_path),
                        timeout_seconds=float(meta.get("max_test_timeout_sec") or 180.0),
                    )
                    trace_events.append(result)
                    emit_cmd("terminalbench.run_tests.done", result)
                    test_output = (result.get("stdout") or "") + (
                        ("\n" + result.get("stderr")) if result.get("stderr") else ""
                    )
                    parser_results = _parse_pytest_results(test_output)
                except Exception as exc:
                    trace_events.append(
                        {
                            "event": "terminalbench.test_run_error",
                            "error": str(exc),
                        }
                    )
            if parser_results:
                trace_events.append(
                    {"event": "terminalbench.parser_results", "parser_results": parser_results}
                )
        finally:
            if env.use_docker_compose and not managed_by_runtime:
                emit_cmd("terminalbench.container.stopping", None, project=env.compose_project)
                down_out = env.compose_down(on_event=emit_env_stream)
                trace_events.append(down_out)
                emit_cmd("terminalbench.container.stopped", down_out, project=env.compose_project)

        state.output = {
            "message": {"role": "assistant", "content": test_output},
            "traj": traj,
            "usage": usage_total,
            "trace_events": trace_events,
        }
        state.stop_reason = StopReason.COMPLETED
        return state


def _build_terminalbench_agent(
    model_entry: ProjectModelEntry,
    provider: ProjectProviderConfig,
) -> TerminusOfficialAgent:
    _ = provider
    return TerminusOfficialAgent(model_config=model_entry.config)


@declare_agent(agent_id="terminalbench_official_agent")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="terminalbench_official_agent",
        factory=_build_terminalbench_agent,
    )
