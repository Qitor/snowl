from __future__ import annotations

import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from snowl.bench import check_benchmark_conformance, list_benchmarks
from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter, OSWorldScorer
from snowl.core import EnvSpec, ScoreContext, TaskResult, TaskStatus
from snowl.envs import GuiEnv
from snowl.tools import build_gui_tools


def _write_osworld_fixture(root: Path) -> None:
    (root / "examples" / "chrome").mkdir(parents=True, exist_ok=True)
    (root / "test_all.json").write_text(
        json.dumps({"chrome": ["id-1", "id-2"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for idx in ("id-1", "id-2"):
        payload = {
            "id": idx,
            "instruction": f"Open tab {idx}",
            "snapshot": "init_state",
            "proxy": False,
            "related_apps": ["chrome"],
            "config": [],
            "trajectory": [],
            "evaluator": {"func": "exact_match"},
            "source": "unit",
        }
        (root / "examples" / "chrome" / f"{idx}.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )


def test_osworld_adapter_registered_and_conformance(tmp_path: Path) -> None:
    _write_osworld_fixture(tmp_path)
    names = {entry["name"] for entry in list_benchmarks()}
    assert "osworld" in names
    report = check_benchmark_conformance("osworld", benchmark_args=[f"dataset_path={tmp_path}"])
    assert report["ok"] is True


def test_osworld_adapter_filters_and_determinism(tmp_path: Path) -> None:
    _write_osworld_fixture(tmp_path)
    adapter = OSWorldBenchmarkAdapter(dataset_path=str(tmp_path))
    tasks_a = adapter.load_tasks(split="test")
    tasks_b = adapter.load_tasks(split="test")
    ids_a = [s["id"] for s in tasks_a[0].iter_samples()]
    ids_b = [s["id"] for s in tasks_b[0].iter_samples()]
    assert ids_a == ids_b
    filtered = adapter.load_tasks(split="test", filters={"domain": "chrome"})
    assert len(list(filtered[0].iter_samples())) == 2


def test_gui_env_and_built_in_tools() -> None:
    env = GuiEnv(
        env_spec=EnvSpec(
            env_type="gui",
            provided_ops=("gui.action", "gui.click", "gui.type", "gui.key", "gui.scroll", "gui.wait", "gui.terminate"),
        )
    )
    tools = build_gui_tools(env)
    by_name = {t.name: t for t in tools}
    click_out = by_name["gui_click"].callable(10.0, 20.0, "left", 1)
    assert click_out["event"] == "gui.action"
    term_out = by_name["gui_terminate"].callable("success")
    assert term_out["event"] == "gui.action"


def test_gui_env_real_container_contract(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    posts: list[tuple[str, object]] = []

    def fake_subprocess_run(cmd, capture_output=None, text=None, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(("run", " ".join(cmd)))
        if cmd[:3] == ["docker", "run", "-d"]:
            return SimpleNamespace(returncode=0, stdout="container-id-123\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    class FakeResp:
        def __init__(
            self,
            status_code: int,
            content: bytes = b"",
            text: str = "ok",
            json_payload: dict | None = None,
        ) -> None:
            self.status_code = status_code
            self.content = content
            self.text = text
            self._json_payload = json_payload or {}

        def json(self):  # type: ignore[no-untyped-def]
            return dict(self._json_payload)

    def fake_get(url, timeout=None):  # type: ignore[no-untyped-def]
        calls.append(("get", str(url)))
        if str(url).endswith("/screenshot"):
            return FakeResp(200, content=b"fake-image")
        if str(url).endswith("/accessibility"):
            return FakeResp(200, json_payload={"AT": "tree"})
        if str(url).endswith("/terminal"):
            return FakeResp(200, json_payload={"output": "pwd"})
        return FakeResp(404)

    def fake_post(url, json=None, timeout=None):  # type: ignore[no-untyped-def]
        calls.append(("post", str(url)))
        posts.append((str(url), json))
        if str(url).endswith("/start_recording"):
            return FakeResp(200, text="{\"status\":\"success\"}")
        if str(url).endswith("/end_recording"):
            return FakeResp(200, content=b"mp4")
        return FakeResp(200, text="{\"status\":\"ok\"}")

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)
    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)

    env = GuiEnv(
        env_spec=EnvSpec(
            env_type="gui",
            provided_ops=("gui.action", "gui.click", "gui.type", "gui.key", "gui.scroll", "gui.wait", "gui.terminate"),
        )
    )
    started = env.start_container(image="happysixd/osworld-docker", cap_add=["NET_ADMIN"])
    assert started["exit_code"] == 0
    obs = env.observe(include_accessibility=True, include_terminal=True)
    assert obs["status_code"] == 200
    assert obs["accessibility_tree"] == "tree"
    assert obs["terminal_output"] == "pwd"
    act = env.execute_action({"action_type": "HOTKEY", "parameters": {"keys": ["ctrl", "l"]}})
    assert act["event"] == "gui.action"
    rec_start = env.start_recording()
    assert rec_start["ok"] is True
    rec_stop = env.end_recording()
    assert rec_stop["ok"] is True
    assert rec_stop["bytes"] == 3
    ev = env.evaluate({"done_status": "success"})
    assert ev["score"] == 1.0
    stopped = env.stop_container()
    assert stopped["event"] == "gui.container.stop"

    assert any(kind == "get" and url.endswith("/screenshot") for kind, url in calls)
    assert any(kind == "post" and url.endswith("/execute") for kind, url in calls)
    assert any(kind == "post" and url.endswith("/start_recording") for kind, url in calls)
    assert any(kind == "post" and url.endswith("/end_recording") for kind, url in calls)
    run_cmds = [cmd for kind, cmd in calls if kind == "run"]
    assert any("--cap-add NET_ADMIN" in cmd for cmd in run_cmds)
    execute_payloads = [payload for url, payload in posts if url.endswith("/execute")]
    assert any(
        "pyautogui.hotkey('ctrl', 'l')" in str((payload or {}).get("command", ["", "", ""])[2])
        for payload in execute_payloads
        if isinstance(payload, dict)
    )


def test_gui_env_action_mapping_coverage() -> None:
    env = GuiEnv(
        env_spec=EnvSpec(
            env_type="gui",
            provided_ops=("gui.action", "gui.click", "gui.type", "gui.key", "gui.scroll", "gui.wait", "gui.terminate"),
        )
    )
    drag = env._action_to_execute_payload({"action_type": "DRAG_TO", "parameters": {"x": 12, "y": 34}})
    assert "pyautogui.dragTo" in str((drag or {}).get("command", ["", "", ""])[2])
    scroll = env._action_to_execute_payload({"action_type": "SCROLL", "parameters": {"dx": 1, "dy": -2}})
    assert "pyautogui.hscroll(1)" in str((scroll or {}).get("command", ["", "", ""])[2])
    assert "pyautogui.vscroll(-2)" in str((scroll or {}).get("command", ["", "", ""])[2])
    key_down = env._action_to_execute_payload({"action_type": "KEY_DOWN", "parameters": {"key": "ctrl"}})
    assert "pyautogui.keyDown('ctrl')" in str((key_down or {}).get("command", ["", "", ""])[2])
    key_up = env._action_to_execute_payload({"action_type": "KEY_UP", "parameters": {"key": "ctrl"}})
    assert "pyautogui.keyUp('ctrl')" in str((key_up or {}).get("command", ["", "", ""])[2])
    right_click = env._action_to_execute_payload({"action_type": "RIGHT_CLICK", "parameters": {"x": 10, "y": 20}})
    assert "pyautogui.rightClick" in str((right_click or {}).get("command", ["", "", ""])[2])
    type_alias = env._action_to_execute_payload({"action_type": "TYPE", "parameters": {"text": "hello"}})
    assert "pyautogui.typewrite('hello')" in str((type_alias or {}).get("command", ["", "", ""])[2])
    key_alias = env._action_to_execute_payload({"action_type": "KEY", "parameters": {"key": "enter"}})
    assert "pyautogui.press('enter')" in str((key_alias or {}).get("command", ["", "", ""])[2])
    type_top_level = env._action_to_execute_payload({"action_type": "TYPE", "text": "hi"})
    assert "pyautogui.typewrite('hi')" in str((type_top_level or {}).get("command", ["", "", ""])[2])
    key_combo = env._action_to_execute_payload({"action_type": "KEY", "key": "ctrl+l"})
    assert "pyautogui.hotkey('ctrl', 'l')" in str((key_combo or {}).get("command", ["", "", ""])[2])
    click_type = env._action_to_execute_payload({"action_type": "CLICK", "click_type": "RIGHT"})
    assert "pyautogui.click(button='right')" in str((click_type or {}).get("command", ["", "", ""])[2])
    with pytest.raises(ValueError):
        env._action_to_execute_payload({"action_type": "UNSUPPORTED", "parameters": {}})


def test_gui_env_evaluate_done_status_success() -> None:
    env = GuiEnv(
        env_spec=EnvSpec(
            env_type="gui",
            provided_ops=("gui.action", "gui.click", "gui.type", "gui.key", "gui.scroll", "gui.wait", "gui.terminate"),
        )
    )
    out = env.evaluate({"done_status": "success"})
    assert out["score"] == 1.0
    assert out["simulated"] is True


def test_gui_env_evaluate_done_status_failed() -> None:
    env = GuiEnv(
        env_spec=EnvSpec(
            env_type="gui",
            provided_ops=("gui.action", "gui.click", "gui.type", "gui.key", "gui.scroll", "gui.wait", "gui.terminate"),
        )
    )
    out = env.evaluate({"done_status": "failed"})
    assert out["score"] == 0.0
    assert out["simulated"] is True


def test_osworld_scorer_semantics() -> None:
    scorer = OSWorldScorer()
    result = TaskResult(
        task_id="osworld:test",
        agent_id="a1",
        sample_id="s1",
        seed=1,
        status=TaskStatus.SUCCESS,
        final_output={"content": "DONE"},
        payload={"osworld_score": 0.75},
    )
    out = scorer.score(result, {}, ScoreContext(task_id="osworld:test", agent_id="a1"))
    assert out["accuracy"].value == 0.75

    out2 = scorer.score(
        TaskResult(
            task_id="osworld:test",
            agent_id="a1",
            sample_id="s1",
            seed=1,
            status=TaskStatus.SUCCESS,
            final_output={"content": "DONE"},
        ),
        {"trace_events": [{"event": "osworld.evaluate", "score": 1.0}]},
        ScoreContext(task_id="osworld:test", agent_id="a1"),
    )
    assert out2["accuracy"].value == 1.0


def test_osworld_official_example_modules_importable() -> None:
    root = Path(__file__).resolve().parents[1]
    example_dir = root / "examples" / "osworld-official"
    for name in ("task.py", "agent.py", "scorer.py", "tool.py"):
        path = example_dir / name
        module_name = f"example_osw_{name.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
