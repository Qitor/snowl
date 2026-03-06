from __future__ import annotations

import sys
import shutil
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest

from snowl.benchmarks.osworld import evaluator as osworld_evaluator
from snowl.benchmarks.osworld.evaluator import evaluate_task, run_setup_config


class _Resp:
    def __init__(self, status_code: int, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text


def test_run_setup_config_calls_expected_routes(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def _fake_post(url, json=None, timeout=None):  # type: ignore[no-untyped-def]
        calls.append((str(url), dict(json or {})))
        return _Resp(200, "ok")

    monkeypatch.setattr("requests.post", _fake_post)
    out = run_setup_config(
        endpoint="http://localhost:5000",
        setup_config=[
            {"type": "execute", "parameters": {"command": ["echo", "hi"]}},
            {"type": "open", "parameters": {"path": "/tmp/a.txt"}},
        ],
    )

    assert len(out) == 2
    assert out[0]["ok"] is True
    assert out[1]["ok"] is True
    assert calls[0][0].endswith("/setup/execute")
    assert calls[1][0].endswith("/setup/open_file")


def test_evaluate_task_single_metric(monkeypatch) -> None:
    # Avoid touching reference imports in unit test.
    monkeypatch.setattr("snowl.benchmarks.osworld.evaluator._ensure_import_path", lambda: None)

    class FakeController:
        def __init__(self, vm_ip: str, server_port: int) -> None:
            self.vm_ip = vm_ip
            self.server_port = server_port

        def get_vm_platform(self):  # type: ignore[no-untyped-def]
            return "linux"

        def get_vm_screen_size(self):  # type: ignore[no-untyped-def]
            return (1920, 1080)

    mod = ModuleType("desktop_env.controllers.python")
    mod.PythonController = FakeController  # type: ignore[attr-defined]
    sys.modules["desktop_env.controllers.python"] = mod

    monkeypatch.setattr(
        "snowl.benchmarks.osworld.evaluator._load_getter",
        lambda _name: (lambda _env, cfg: cfg.get("value")),
    )
    monkeypatch.setattr(
        "snowl.benchmarks.osworld.evaluator._load_metric",
        lambda _name: (lambda result, expected, **_opts: 1.0 if result == expected else 0.0),
    )

    out = evaluate_task(
        endpoint="http://localhost:5000",
        evaluator={
            "func": "dummy_metric",
            "result": {"type": "dummy", "value": "A"},
            "expected": {"type": "dummy", "value": "A"},
            "options": {},
        },
        action_history=[],
        sample_id="s1",
        task_id="t1",
    )
    assert out["simulated"] is False
    assert out["score"] == 1.0


def test_load_callable_bypasses_category_init(monkeypatch) -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    tmp_root = workspace_root / f".tmp_osw_eval_{uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=False)
    try:
        ref_root = tmp_root / "ref"
        metrics_dir = ref_root / "desktop_env" / "evaluators" / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (ref_root / "desktop_env" / "__init__.py").write_text("", encoding="utf-8")
        (ref_root / "desktop_env" / "evaluators" / "__init__.py").write_text("", encoding="utf-8")
        (metrics_dir / "__init__.py").write_text(
            "raise RuntimeError('metrics init should not run')\n",
            encoding="utf-8",
        )
        (metrics_dir / "utils.py").write_text(
            "def add(a, b):\n"
            "    return a + b\n",
            encoding="utf-8",
        )
        (metrics_dir / "general.py").write_text(
            "from desktop_env.evaluators.metrics.utils import add\n"
            "\n"
            "def match_in_list(result, rules):\n"
            "    return float(add(1, 0))\n",
            encoding="utf-8",
        )

        for name in (
            "desktop_env.evaluators.metrics",
            "desktop_env.evaluators.metrics.general",
            "desktop_env.evaluators.metrics.utils",
        ):
            sys.modules.pop(name, None)

        osworld_evaluator._FUNC_CACHE.clear()
        monkeypatch.setattr(osworld_evaluator, "_reference_root", lambda: ref_root)
        fn = osworld_evaluator._load_callable(category="metrics", func_name="match_in_list")
        assert callable(fn)
        assert float(fn(None, None)) == 1.0
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_load_callable_reports_fitz_conflict_hint(monkeypatch) -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    tmp_root = workspace_root / f".tmp_osw_eval_{uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=False)
    try:
        ref_root = tmp_root / "ref"
        metrics_dir = ref_root / "desktop_env" / "evaluators" / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (ref_root / "desktop_env" / "__init__.py").write_text("", encoding="utf-8")
        (ref_root / "desktop_env" / "evaluators" / "__init__.py").write_text("", encoding="utf-8")
        (metrics_dir / "__init__.py").write_text("", encoding="utf-8")
        (metrics_dir / "frontend_case.py").write_text(
            "import frontend\n"
            "\n"
            "def match_in_list(result, rules):\n"
            "    return 0.0\n",
            encoding="utf-8",
        )
        for name in (
            "desktop_env.evaluators.metrics",
            "desktop_env.evaluators.metrics.frontend_case",
        ):
            sys.modules.pop(name, None)
        osworld_evaluator._FUNC_CACHE.clear()
        monkeypatch.setattr(osworld_evaluator, "_reference_root", lambda: ref_root)
        with pytest.raises(RuntimeError, match="conflicting `fitz` package"):
            osworld_evaluator._load_callable(category="metrics", func_name="match_in_list")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
