from __future__ import annotations

import io
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from snowl.ui import LiveConsoleRenderer, load_panel_config


def test_panel_config_includes_required_types_for_three_benchmarks() -> None:
    sr = load_panel_config(benchmark_name="strongreject")
    tb = load_panel_config(benchmark_name="terminalbench")
    osw = load_panel_config(benchmark_name="osworld")

    assert {"overview", "stage_widget", "metric_spotlight", "task_queue", "task_detail", "model_io", "scorer_explain", "failures"}.issubset(sr.specs.keys())
    assert {"overview", "stage_widget", "metric_spotlight", "task_queue", "task_detail", "env_timeline", "action_stream", "observation_stream", "scorer_explain", "failures"}.issubset(tb.specs.keys())
    assert {"overview", "stage_widget", "metric_spotlight", "task_queue", "task_detail", "env_timeline", "action_stream", "observation_stream", "scorer_explain", "failures"}.issubset(osw.specs.keys())


def test_panel_config_precedence_default_then_benchmark_then_user(tmp_path: Path) -> None:
    user = tmp_path / "panels.yml"
    user.write_text(
        """
panels:
  - type: scorer_explain
    title: CUSTOM JUDGE PANEL
    source: scorer_explain
    visibility: always
layout:
  left: [task_queue, task_detail]
  right: [scorer_explain, failures]
""",
        encoding="utf-8",
    )
    cfg = load_panel_config(benchmark_name="strongreject", project_dir=tmp_path)
    assert cfg.specs["scorer_explain"].title == "CUSTOM JUDGE PANEL"
    assert cfg.layout.right[0] == "scorer_explain"
    assert str(user) in cfg.source_chain[-1]


@dataclass(frozen=True)
class _Task:
    metadata: dict
    env_spec: object


@dataclass(frozen=True)
class _Trial:
    task_id: str
    agent_id: str
    variant_id: str
    sample_id: str
    sample: dict
    task: _Task


@dataclass(frozen=True)
class _Plan:
    mode: str
    task_ids: list[str]
    agent_ids: list[str]
    variant_ids: list[str]
    sample_count: int
    trials: list[_Trial]


def test_renderer_uses_configured_panel_titles_without_benchmark_branching(tmp_path: Path) -> None:
    (tmp_path / "panels.yml").write_text(
        """
panels:
  - type: model_io
    title: RESPONSE WINDOW
    source: model_io
    visibility: always
layout:
  left: [task_queue]
  right: [model_io, failures]
""",
        encoding="utf-8",
    )
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    renderer.configure_panels(benchmark_name="strongreject", project_dir=tmp_path)
    renderer._benchmark_name = "strongreject"

    trial = _Trial(
        task_id="strongreject:test",
        agent_id="chat",
        variant_id="default",
        sample_id="s1",
        sample={"id": "s1", "input": "x"},
        task=_Task(metadata={"benchmark": "strongreject"}, env_spec=object()),
    )
    plan = _Plan(
        mode="single",
        task_ids=["strongreject:test"],
        agent_ids=["chat"],
        variant_ids=["default"],
        sample_count=1,
        trials=[trial],
    )

    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_plan(plan)
    out = buf.getvalue()
    assert "RESPONSE WINDOW" in out


def test_panel_config_fallback_without_yaml_files(monkeypatch) -> None:
    import snowl.ui.panels as panel_mod

    monkeypatch.setattr(panel_mod, "_load_yaml", lambda path: {})
    cfg = panel_mod.load_panel_config(benchmark_name="strongreject")
    assert cfg.layout.left
    assert cfg.layout.right
    assert "task_queue" in cfg.specs
    assert "model_io" in cfg.specs
