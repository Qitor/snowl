from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from snowl.bench import check_benchmark_conformance, list_benchmarks
from snowl.benchmarks.terminalbench import (
    TerminalBenchBenchmarkAdapter,
    TerminalBenchScorer,
)
from snowl.core import AgentContext, AgentState, EnvSpec, ScoreContext, StopReason, TaskResult, TaskStatus
from snowl.envs import TerminalEnv
from snowl.model import OpenAICompatibleConfig
from snowl.tools import build_terminal_tools


def _write_task_dir(root: Path, task_id: str, *, instruction: str, difficulty: str, category: str) -> None:
    task_dir = root / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.yaml").write_text(
        textwrap.dedent(
            f"""\
            instruction: |-
              {instruction}
            difficulty: {difficulty}
            category: {category}
            parser_name: pytest
            max_agent_timeout_sec: 120
            max_test_timeout_sec: 60
            """
        ),
        encoding="utf-8",
    )
    (task_dir / "run-tests.sh").write_text("#!/bin/bash\necho ok\n", encoding="utf-8")
    (task_dir / "docker-compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (task_dir / "tests").mkdir(parents=True, exist_ok=True)


def test_terminalbench_adapter_registered_and_conformance(tmp_path: Path) -> None:
    _write_task_dir(tmp_path, "hello-world", instruction="Create hello.txt", difficulty="easy", category="file-ops")
    _write_task_dir(tmp_path, "json-task", instruction="Process JSON", difficulty="medium", category="data")

    names = {entry["name"] for entry in list_benchmarks()}
    assert "terminalbench" in names

    report = check_benchmark_conformance(
        "terminalbench",
        benchmark_args=[f"dataset_path={tmp_path}"],
    )
    assert report["ok"] is True


def test_terminalbench_adapter_filters_and_determinism(tmp_path: Path) -> None:
    _write_task_dir(tmp_path, "a-task", instruction="Task A", difficulty="easy", category="file-ops")
    _write_task_dir(tmp_path, "b-task", instruction="Task B", difficulty="hard", category="network")
    adapter = TerminalBenchBenchmarkAdapter(dataset_path=str(tmp_path))

    tasks_a = adapter.load_tasks(split="test")
    tasks_b = adapter.load_tasks(split="test")
    ids_a = [s["id"] for s in tasks_a[0].iter_samples()]
    ids_b = [s["id"] for s in tasks_b[0].iter_samples()]
    assert ids_a == ids_b

    filtered = adapter.load_tasks(split="test", filters={"difficulty": "hard"})
    samples = list(filtered[0].iter_samples())
    assert len(samples) == 1
    assert samples[0]["metadata"]["task_id"] == "b-task"


def test_terminalbench_adapter_detects_docker_compose_yml(tmp_path: Path) -> None:
    task_dir = tmp_path / "yml-task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.yaml").write_text(
        "instruction: |\n  echo yml\nparser_name: pytest\nsplit: test\n",
        encoding="utf-8",
    )
    (task_dir / "run-tests.sh").write_text("#!/bin/bash\necho ok\n", encoding="utf-8")
    (task_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    adapter = TerminalBenchBenchmarkAdapter(dataset_path=str(tmp_path))
    tasks = adapter.load_tasks(split="test", limit=1)
    sample = next(tasks[0].iter_samples())
    assert sample["metadata"]["docker_compose_path"].endswith("docker-compose.yml")


def test_terminal_env_and_built_in_tools(tmp_path: Path) -> None:
    env = TerminalEnv(
        env_spec=EnvSpec(
            env_type="terminal",
            provided_ops=("terminal.exec", "terminal.send_keys", "terminal.capture", "terminal.wait", "process.run"),
        ),
        workdir=str(tmp_path),
    )
    tools = build_terminal_tools(env)
    name_to_tool = {t.name: t for t in tools}
    result = name_to_tool["terminal_exec"].callable("echo hello", 10.0)
    assert result["exit_code"] == 0
    captured = name_to_tool["terminal_capture"].callable()
    assert "hello" in captured


def test_terminal_env_compose_lifecycle(monkeypatch, tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yaml"
    compose_file.write_text(
        textwrap.dedent(
            """\
            services:
              client:
                image: busybox
                command: ["sh", "-c", "sleep infinity"]
            """
        ),
        encoding="utf-8",
    )

    seen: list[tuple[list[str], dict[str, str] | None]] = []

    def response(cmd: list[str]) -> dict[str, object]:
        if "exec" in cmd:
            return {"returncode": 0, "stdout": "exec-ok\n", "stderr": ""}
        return {"returncode": 0, "stdout": "ok\n", "stderr": ""}

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        env = kwargs.get("env")
        seen.append((list(cmd), dict(env) if isinstance(env, dict) else None))
        return _FakePopen(cmd, response=response, **kwargs)

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    env = TerminalEnv(
        env_spec=EnvSpec(
            env_type="terminal",
            provided_ops=("terminal.exec", "terminal.send_keys", "terminal.capture", "terminal.wait", "process.run"),
        ),
        workdir=str(tmp_path),
        compose_file=str(compose_file),
        use_docker_compose=True,
        compose_build=False,
        compose_project="snowl-test",
    )

    up = env.compose_up()
    assert up["exit_code"] == 0
    out = env.exec("echo hello")
    assert out["exit_code"] == 0
    assert "exec-ok" in out["stdout"]
    test_out = env.run_tests(run_tests_path=str(tmp_path / "run-tests.sh"))
    assert test_out["event"] == "terminal.run_tests"
    down = env.compose_down()
    assert down["exit_code"] == 0

    cmds = [cmd for cmd, _ in seen]
    assert any(cmd[:3] == ["docker", "compose", "-p"] and "up" in cmd for cmd in cmds)
    assert any("exec" in cmd and "client" in cmd for cmd in cmds)
    assert any("down" in cmd for cmd in cmds)
    compose_env = next((env_map for cmd, env_map in seen if "up" in cmd and env_map), None)
    assert compose_env is not None
    assert compose_env.get("T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME")
    assert compose_env.get("T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME")
    assert compose_env.get("T_BENCH_TEST_DIR") == "/tests"
    assert compose_env.get("T_BENCH_TASK_LOGS_PATH")


def test_terminalbench_scorer_from_pytest_output_and_trace() -> None:
    scorer = TerminalBenchScorer()
    result = TaskResult(
        task_id="terminalbench:test",
        agent_id="a1",
        sample_id="s1",
        seed=1,
        status=TaskStatus.SUCCESS,
        final_output={
            "content": (
                "...\n"
                "================ short test summary info ================\n"
                "PASSED tests/test_outputs.py::test_ok\n"
                "FAILED tests/test_outputs.py::test_bad - AssertionError\n"
            )
        },
    )
    out = scorer.score(
        result,
        {},
        ScoreContext(task_id="terminalbench:test", agent_id="a1", sample_metadata={"parser_name": "pytest"}),
    )
    assert out["accuracy"].value == 0.0
    assert out["pass_rate"].value == 0.5

    out2 = scorer.score(
        result,
        {"trace_events": [{"event": "terminalbench.parser_results", "parser_results": {"test_ok": "passed"}}]},
        ScoreContext(task_id="terminalbench:test", agent_id="a1", sample_metadata={"parser_name": "pytest"}),
    )
    assert out2["accuracy"].value == 1.0


def test_terminalbench_official_example_modules_importable() -> None:
    root = Path(__file__).resolve().parents[1]
    example_dir = root / "examples" / "terminalbench-official"
    for name in ("task.py", "agent.py", "scorer.py", "tool.py"):
        path = example_dir / name
        module_name = f"example_tb_{name.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)


def _load_terminalbench_official_agent_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "examples" / "terminalbench-official" / "agent.py"
    module_name = "example_tb_agent_retry_module"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _FakeModelClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls = 0
        self.model = "fake-model"
        self.message_batches: list[list[dict[str, object]]] = []

    async def generate(self, _messages, temperature=0.2):
        _ = temperature
        self.message_batches.append([dict(msg) for msg in _messages])
        idx = min(self.calls, len(self._responses) - 1)
        content = self._responses[idx]
        self.calls += 1
        return SimpleNamespace(
            message={"role": "assistant", "content": content},
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
        )


class _FakeTerminalEnv:
    def __init__(self, captures: list[str] | None = None) -> None:
        self.use_docker_compose = False
        self.compose_project = "fake-proj"
        self.compose_file = None
        self.sent: list[dict[str, object]] = []
        self._captures = list(captures) if captures is not None else ["terminal-state"]
        self._capture_index = 0

    def capture(self) -> str:
        idx = min(self._capture_index, len(self._captures) - 1)
        value = self._captures[idx]
        self._capture_index += 1
        return value

    def send_keys(
        self,
        keystrokes: str,
        *,
        is_blocking: bool = False,
        timeout_sec: float = 180.0,
    ) -> dict[str, object]:
        evt = {
            "keystrokes": keystrokes,
            "is_blocking": is_blocking,
            "timeout_sec": timeout_sec,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "duration_ms": 1,
        }
        self.sent.append(evt)
        return evt


def _build_context(tmp_path: Path, env: _FakeTerminalEnv, events: list[dict[str, object]]) -> AgentContext:
    sample = {
        "id": "tb-s1",
        "input": "solve task",
        "metadata": {
            "task_id": "tb-task",
            "task_root": str(tmp_path),
            "run_tests_path": "",
            "docker_compose_path": "",
        },
    }
    return AgentContext(
        task_id="terminalbench:test",
        sample_id="tb-s1",
        metadata={
            "sample": sample,
            "__snowl_emit_event": lambda evt: events.append(dict(evt)),
            "__snowl_container_session": SimpleNamespace(kind="terminal_compose", env=env),
        },
    )


def _terminal_model_config() -> OpenAICompatibleConfig:
    return OpenAICompatibleConfig(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="test-model",
        timeout=30,
        max_retries=1,
    )


def test_terminalbench_official_agent_retries_parse_error_then_recovers(tmp_path: Path) -> None:
    module = _load_terminalbench_official_agent_module()
    valid_payload = json.dumps(
        {
            "state_analysis": "ok",
            "explanation": "continue",
            "commands": [],
            "is_task_complete": True,
        }
    )
    fake_client = _FakeModelClient(["not-json", "{bad", valid_payload])
    agent = module.TerminusOfficialAgent(model_config=_terminal_model_config(), max_episodes=1, max_parse_retries=3)
    agent._client = fake_client

    env = _FakeTerminalEnv()
    events: list[dict[str, object]] = []
    context = _build_context(tmp_path, env, events)
    state = AgentState(messages=[{"role": "user", "content": "go"}])

    out = asyncio.run(agent.run(state, context))

    assert out.stop_reason == StopReason.COMPLETED
    assert fake_client.calls == 3
    assert out.output is not None
    parse_errors = [e for e in out.output["trace_events"] if e.get("event") == "terminalbench.parse_error"]
    assert len(parse_errors) == 2
    assert [e.get("parse_attempt") for e in parse_errors] == [1, 2]


def test_terminalbench_official_agent_fails_after_parse_retry_exhausted(tmp_path: Path) -> None:
    module = _load_terminalbench_official_agent_module()
    fake_client = _FakeModelClient(["invalid-1", "invalid-2", "invalid-3"])
    agent = module.TerminusOfficialAgent(model_config=_terminal_model_config(), max_episodes=1, max_parse_retries=3)
    agent._client = fake_client

    env = _FakeTerminalEnv()
    events: list[dict[str, object]] = []
    context = _build_context(tmp_path, env, events)
    state = AgentState(messages=[{"role": "user", "content": "go"}])

    with pytest.raises(RuntimeError, match="parse failed after 3 attempts"):
        asyncio.run(agent.run(state, context))
    assert fake_client.calls == 3


def test_terminalbench_official_agent_records_raw_model_traj(tmp_path: Path) -> None:
    module = _load_terminalbench_official_agent_module()
    response = json.dumps(
        {
            "state_analysis": "ok",
            "explanation": "continue",
            "commands": [],
            "is_task_complete": True,
        }
    )
    fake_client = _FakeModelClient([response])
    agent = module.TerminusOfficialAgent(model_config=_terminal_model_config(), max_episodes=1)
    agent._client = fake_client

    env = _FakeTerminalEnv()
    events: list[dict[str, object]] = []
    context = _build_context(tmp_path, env, events)
    state = AgentState(messages=[{"role": "user", "content": "go"}])

    out = asyncio.run(agent.run(state, context))

    assert out.output is not None
    traj = out.output["traj"]
    assert traj == [
        {
            "role": "user",
            "content": fake_client.message_batches[0][0]["content"],
        },
        {
            "role": "assistant",
            "content": response,
        },
    ]
    assert "solve task" in str(traj[0]["content"])


def test_terminalbench_official_agent_uses_official_message_history_progression(tmp_path: Path) -> None:
    module = _load_terminalbench_official_agent_module()
    first_response = json.dumps(
        {
            "state_analysis": "episode-1",
            "explanation": "continue",
            "commands": [],
            "is_task_complete": False,
        }
    )
    second_response = json.dumps(
        {
            "state_analysis": "episode-2",
            "explanation": "done",
            "commands": [],
            "is_task_complete": True,
        }
    )
    fake_client = _FakeModelClient([first_response, second_response])
    agent = module.TerminusOfficialAgent(model_config=_terminal_model_config(), max_episodes=2)
    agent._client = fake_client

    env = _FakeTerminalEnv(captures=["initial-screen", "after-episode-1", "after-episode-2"])
    events: list[dict[str, object]] = []
    context = _build_context(tmp_path, env, events)
    state = AgentState(messages=[{"role": "user", "content": "go"}])

    out = asyncio.run(agent.run(state, context))

    assert out.stop_reason == StopReason.COMPLETED
    assert len(fake_client.message_batches) == 2

    first_batch = fake_client.message_batches[0]
    assert len(first_batch) == 1
    assert first_batch[0]["role"] == "user"
    assert "solve task" in str(first_batch[0]["content"])
    assert "initial-screen" in str(first_batch[0]["content"])

    second_batch = fake_client.message_batches[1]
    assert second_batch == [
        {"role": "user", "content": first_batch[0]["content"]},
        {"role": "assistant", "content": first_response},
        {"role": "user", "content": "after-episode-1"},
    ]

    assert out.output is not None
    assert out.output["traj"] == [
        {"role": "user", "content": first_batch[0]["content"]},
        {"role": "assistant", "content": first_response},
        {"role": "user", "content": "after-episode-1"},
        {"role": "assistant", "content": second_response},
    ]


def test_terminalbench_official_agent_appends_newline_for_blocking_shell_command(tmp_path: Path) -> None:
    module = _load_terminalbench_official_agent_module()
    response = json.dumps(
        {
            "state_analysis": "ok",
            "explanation": "run shell command",
            "commands": [
                {
                    "keystrokes": "ls -la /app/",
                    "is_blocking": True,
                    "timeout_sec": 30,
                }
            ],
            "is_task_complete": True,
        }
    )
    fake_client = _FakeModelClient([response])
    agent = module.TerminusOfficialAgent(model_config=_terminal_model_config(), max_episodes=1)
    agent._client = fake_client

    env = _FakeTerminalEnv()
    events: list[dict[str, object]] = []
    context = _build_context(tmp_path, env, events)
    state = AgentState(messages=[{"role": "user", "content": "go"}])

    out = asyncio.run(agent.run(state, context))

    assert out.stop_reason == StopReason.COMPLETED
    assert len(env.sent) == 1
    assert env.sent[0]["keystrokes"] == "ls -la /app/\n"
    assert env.sent[0]["is_blocking"] is True


def test_terminalbench_official_agent_does_not_block_on_background_tmux_command(tmp_path: Path) -> None:
    module = _load_terminalbench_official_agent_module()
    response = json.dumps(
        {
            "state_analysis": "ok",
            "explanation": "launch a background task",
            "commands": [
                {
                    "keystrokes": "python worker.py &\n",
                    "is_blocking": True,
                    "timeout_sec": 30,
                }
            ],
            "is_task_complete": True,
        }
    )
    fake_client = _FakeModelClient([response])
    agent = module.TerminusOfficialAgent(model_config=_terminal_model_config(), max_episodes=1)
    agent._client = fake_client

    env = _FakeTerminalEnv()
    events: list[dict[str, object]] = []
    context = _build_context(tmp_path, env, events)
    state = AgentState(messages=[{"role": "user", "content": "go"}])

    out = asyncio.run(agent.run(state, context))

    assert out.stop_reason == StopReason.COMPLETED
    assert len(env.sent) == 1
    assert env.sent[0]["keystrokes"] == "python worker.py &\n"
    assert env.sent[0]["is_blocking"] is False


def test_terminalbench_official_agent_does_not_block_on_heredoc_terminator(tmp_path: Path) -> None:
    module = _load_terminalbench_official_agent_module()
    response = json.dumps(
        {
            "state_analysis": "ok",
            "explanation": "finish heredoc",
            "commands": [
                {
                    "keystrokes": "EOF\n",
                    "is_blocking": True,
                    "timeout_sec": 30,
                }
            ],
            "is_task_complete": True,
        }
    )
    fake_client = _FakeModelClient([response])
    agent = module.TerminusOfficialAgent(model_config=_terminal_model_config(), max_episodes=1)
    agent._client = fake_client

    env = _FakeTerminalEnv()
    events: list[dict[str, object]] = []
    context = _build_context(tmp_path, env, events)
    state = AgentState(messages=[{"role": "user", "content": "go"}])

    out = asyncio.run(agent.run(state, context))

    assert out.stop_reason == StopReason.COMPLETED
    assert len(env.sent) == 1
    assert env.sent[0]["keystrokes"] == "EOF\n"
    assert env.sent[0]["is_blocking"] is False


class _FakeStream:
    def __init__(self, text: str = "") -> None:
        self._chunks = text.splitlines(keepends=True)

    def readline(self) -> str:
        if self._chunks:
            return self._chunks.pop(0)
        return ""

    def close(self) -> None:
        return None


class _FakePopen:
    def __init__(self, cmd, *, response, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        payload = response(list(cmd))
        self.returncode = int(payload.get("returncode", 0))
        self.stdout = _FakeStream(str(payload.get("stdout", "")))
        self.stderr = _FakeStream(str(payload.get("stderr", "")))
        self._killed = False

    def poll(self):  # type: ignore[no-untyped-def]
        return self.returncode

    def wait(self):  # type: ignore[no-untyped-def]
        return self.returncode

    def kill(self) -> None:
        self._killed = True
        self.returncode = -9


def test_terminal_env_compose_tmux_session_created_and_capture_uses_tmux(monkeypatch, tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yaml"
    compose_file.write_text(
        textwrap.dedent(
            """\
            services:
              client:
                image: busybox
                command: ["sh", "-c", "sleep infinity"]
            """
        ),
        encoding="utf-8",
    )
    seen: list[list[str]] = []
    state = {"session_exists": False}

    def response(cmd: list[str]) -> dict[str, object]:
        seen.append(list(cmd))
        command_text = " ".join(cmd)
        if " up -d" in f" {command_text} ":
            return {"returncode": 0, "stdout": "up ok\n"}
        if "tmux has-session" in command_text:
            return {"returncode": 0 if state["session_exists"] else 1}
        if "tmux new-session" in command_text:
            state["session_exists"] = True
            return {"returncode": 0, "stdout": "session started\n"}
        if "tmux send-keys" in command_text:
            return {"returncode": 0}
        if "tmux wait" in command_text:
            return {"returncode": 0}
        if "tmux capture-pane" in command_text:
            return {"returncode": 0, "stdout": "pane-output\n"}
        return {"returncode": 0}

    monkeypatch.setattr(
        "subprocess.Popen",
        lambda cmd, **kwargs: _FakePopen(cmd, response=response, **kwargs),
    )

    env = TerminalEnv(
        env_spec=EnvSpec(
            env_type="terminal",
            provided_ops=("terminal.exec", "terminal.send_keys", "terminal.capture", "terminal.wait", "process.run"),
        ),
        workdir=str(tmp_path),
        compose_file=str(compose_file),
        use_docker_compose=True,
        compose_build=False,
        compose_project="snowl-test",
    )

    env.compose_up()
    out = env.send_keys("echo hello\n", is_blocking=True, timeout_sec=10.0)
    captured = env.capture()

    assert out["exit_code"] == 0
    assert captured == "pane-output\n"
    joined = [" ".join(cmd) for cmd in seen]
    assert any("tmux new-session" in cmd for cmd in joined)
    assert any("tmux send-keys" in cmd for cmd in joined)
    assert any("tmux wait" in cmd for cmd in joined)
    assert any("tmux capture-pane" in cmd for cmd in joined)


def test_terminal_env_compose_tmux_session_is_reused(monkeypatch, tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yaml"
    compose_file.write_text(
        textwrap.dedent(
            """\
            services:
              client:
                image: busybox
                command: ["sh", "-c", "sleep infinity"]
            """
        ),
        encoding="utf-8",
    )
    seen: list[list[str]] = []
    state = {"session_exists": False}

    def response(cmd: list[str]) -> dict[str, object]:
        seen.append(list(cmd))
        command_text = " ".join(cmd)
        if " up -d" in f" {command_text} ":
            return {"returncode": 0}
        if "tmux has-session" in command_text:
            return {"returncode": 0 if state["session_exists"] else 1}
        if "tmux new-session" in command_text:
            state["session_exists"] = True
            return {"returncode": 0}
        if "tmux send-keys" in command_text:
            return {"returncode": 0}
        if "tmux wait" in command_text:
            return {"returncode": 0}
        return {"returncode": 0}

    monkeypatch.setattr(
        "subprocess.Popen",
        lambda cmd, **kwargs: _FakePopen(cmd, response=response, **kwargs),
    )

    env = TerminalEnv(
        env_spec=EnvSpec(
            env_type="terminal",
            provided_ops=("terminal.exec", "terminal.send_keys", "terminal.capture", "terminal.wait", "process.run"),
        ),
        workdir=str(tmp_path),
        compose_file=str(compose_file),
        use_docker_compose=True,
        compose_build=False,
        compose_project="snowl-test",
    )

    env.compose_up()
    env.send_keys("pwd\n", is_blocking=True, timeout_sec=5.0)
    env.send_keys("echo again\n", is_blocking=True, timeout_sec=5.0)

    joined = [" ".join(cmd) for cmd in seen]
    assert sum("tmux new-session" in cmd for cmd in joined) == 1
