"""Panel type registry and benchmark/user configurable panel layouts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml


PANEL_TYPES = {
    "overview",
    "stage_widget",
    "metric_spotlight",
    "task_queue",
    "task_detail",
    "qa_prompt",
    "qa_result",
    "event_stream",
    "env_timeline",
    "action_stream",
    "observation_stream",
    "model_io",
    "scorer_explain",
    "compare_board",
    "failures",
}


@dataclass(frozen=True)
class PanelSpec:
    panel_type: str
    title: str
    source: str
    transform: str = "default"
    visibility: str = "always"
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PanelLayout:
    left: list[str] = field(default_factory=list)
    right: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PanelConfig:
    specs: dict[str, PanelSpec]
    layout: PanelLayout
    source_chain: list[str] = field(default_factory=list)


def _builtin_default_parts() -> tuple[dict[str, PanelSpec], PanelLayout]:
    specs = {
        "overview": PanelSpec("overview", "EVAL OVERVIEW", "overview"),
        "stage_widget": PanelSpec("stage_widget", "STAGE", "runtime_state"),
        "metric_spotlight": PanelSpec("metric_spotlight", "METRIC SPOTLIGHT", "metrics"),
        "task_queue": PanelSpec("task_queue", "TASK QUEUE", "task_monitor"),
        "task_detail": PanelSpec("task_detail", "TASK DETAIL", "task_monitor"),
        "event_stream": PanelSpec("event_stream", "EVENT STREAM", "events"),
        "env_timeline": PanelSpec("env_timeline", "ENV TIMELINE", "env_events", visibility="when_env_present"),
        "action_stream": PanelSpec("action_stream", "ACTION STREAM", "action_events"),
        "observation_stream": PanelSpec("observation_stream", "OBSERVATION STREAM", "observation_events"),
        "model_io": PanelSpec("model_io", "MODEL IO", "model_io", visibility="when_model_io_present"),
        "scorer_explain": PanelSpec("scorer_explain", "SCORER EXPLAIN", "scorer_explain", visibility="when_scorer_present"),
        "compare_board": PanelSpec("compare_board", "COMPARE BOARD", "compare"),
        "failures": PanelSpec("failures", "FAILURES", "failures"),
    }
    layout = PanelLayout(
        left=["task_queue", "task_detail", "event_stream", "action_stream", "observation_stream"],
        right=["stage_widget", "metric_spotlight", "env_timeline", "model_io", "scorer_explain", "compare_board", "failures"],
    )
    return specs, layout


def _parse_config_dict(payload: Mapping[str, Any], *, source_label: str) -> tuple[dict[str, PanelSpec], PanelLayout]:
    specs: dict[str, PanelSpec] = {}
    for raw in payload.get("panels", []) or []:
        if not isinstance(raw, Mapping):
            continue
        panel_type = str(raw.get("type", "")).strip()
        if not panel_type:
            continue
        if panel_type not in PANEL_TYPES:
            # allow forward-compatible custom types, but still accept.
            pass
        specs[panel_type] = PanelSpec(
            panel_type=panel_type,
            title=str(raw.get("title") or panel_type.upper()),
            source=str(raw.get("source") or panel_type),
            transform=str(raw.get("transform") or "default"),
            visibility=str(raw.get("visibility") or "always"),
            options=dict(raw.get("options") or {}),
        )

    layout_raw = payload.get("layout", {}) or {}
    left = [str(x) for x in (layout_raw.get("left") or []) if str(x)]
    right = [str(x) for x in (layout_raw.get("right") or []) if str(x)]
    layout = PanelLayout(left=left, right=right)
    _ = source_label
    return specs, layout


def _merge_configs(parts: list[tuple[dict[str, PanelSpec], PanelLayout, str]]) -> PanelConfig:
    merged_specs: dict[str, PanelSpec] = {}
    layout = PanelLayout()
    chain: list[str] = []
    for specs, this_layout, source in parts:
        chain.append(source)
        merged_specs.update(specs)
        if this_layout.left:
            layout = PanelLayout(left=list(this_layout.left), right=list(layout.right))
        if this_layout.right:
            layout = PanelLayout(left=list(layout.left), right=list(this_layout.right))
    if not layout.left and not layout.right:
        # deterministic fallback
        layout = PanelLayout(
            left=["task_queue", "task_detail", "action_stream", "observation_stream"],
            right=["stage_widget", "metric_spotlight", "env_timeline", "model_io", "scorer_explain", "compare_board", "failures"],
        )
    # Ensure every referenced panel_type has a spec so renderer never falls into "loading..." dead state.
    for panel_type in list(layout.left) + list(layout.right):
        if panel_type not in merged_specs:
            merged_specs[panel_type] = PanelSpec(
                panel_type=panel_type,
                title=panel_type.upper(),
                source=panel_type,
            )
    return PanelConfig(specs=merged_specs, layout=layout, source_chain=chain)


def _load_yaml(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping):
        return {}
    return data


def load_panel_config(
    *,
    benchmark_name: str | None = None,
    project_dir: Path | None = None,
    user_override: Path | None = None,
) -> PanelConfig:
    """Load panel config by precedence: default < benchmark < user."""

    root = Path(__file__).resolve().parent / "panel_configs"
    parts: list[tuple[dict[str, PanelSpec], PanelLayout, str]] = []

    default_path = root / "default.yml"
    default_specs, default_layout = _parse_config_dict(_load_yaml(default_path), source_label=str(default_path))
    if not default_specs and not default_layout.left and not default_layout.right:
        default_specs, default_layout = _builtin_default_parts()
        parts.append((default_specs, default_layout, "<builtin-default>"))
    else:
        parts.append((default_specs, default_layout, str(default_path)))

    if benchmark_name:
        bench_path = root / f"{benchmark_name}.yml"
        if bench_path.exists():
            bench_specs, bench_layout = _parse_config_dict(_load_yaml(bench_path), source_label=str(bench_path))
            parts.append((bench_specs, bench_layout, str(bench_path)))

    chosen_user: Path | None = None
    if user_override is not None:
        chosen_user = user_override
    elif project_dir is not None:
        for name in ("panels.yml", "panels.yaml"):
            candidate = project_dir / name
            if candidate.exists():
                chosen_user = candidate
                break

    if chosen_user is not None and chosen_user.exists():
        user_specs, user_layout = _parse_config_dict(_load_yaml(chosen_user), source_label=str(chosen_user))
        parts.append((user_specs, user_layout, str(chosen_user)))

    return _merge_configs(parts)


PanelRenderFn = Callable[[Any, PanelSpec, str], list[str]]


class PanelRegistry:
    """Registry for panel_type renderers."""

    def __init__(self) -> None:
        self._renderers: dict[str, PanelRenderFn] = {}

    def register(self, panel_type: str, fn: PanelRenderFn) -> None:
        self._renderers[panel_type] = fn

    def get(self, panel_type: str) -> PanelRenderFn | None:
        return self._renderers.get(panel_type)

    def list_panel_types(self) -> list[str]:
        return sorted(self._renderers.keys())
