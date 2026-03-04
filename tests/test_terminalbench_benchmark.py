from __future__ import annotations

import importlib.util
import sys
import textwrap
from types import SimpleNamespace
from pathlib import Path

from snowl.bench import check_benchmark_conformance, list_benchmarks
from snowl.benchmarks.terminalbench import (
    TerminalBenchBenchmarkAdapter,
    TerminalBenchScorer,
)
from snowl.core import EnvSpec, ScoreContext, TaskResult, TaskStatus
from snowl.envs import TerminalEnv
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

    def fake_run(cmd, cwd=None, text=None, capture_output=None, timeout=None, env=None):  # type: ignore[no-untyped-def]
        seen.append((list(cmd), dict(env) if isinstance(env, dict) else None))
        if "exec" in cmd:
            return SimpleNamespace(returncode=0, stdout="exec-ok\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

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
