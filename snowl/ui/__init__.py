"""Operator-UI package facade for renderers, events, controls, and panel configs.

Framework role:
- Re-exports monitor contracts and console components used by CLI interactive/non-interactive flows.

Runtime/usage wiring:
- Consumed by eval/CLI code that emits normalized runtime events and renders progress.

Change guardrails:
- Preserve UI contract exports (`UIEvent`, `TaskMonitorState`, etc.) to keep CLI and web observability aligned.
"""

from snowl.ui.console import ConsoleRenderer, LiveConsoleRenderer
from snowl.ui.contracts import (
    EventPhase,
    ScoreExplanation,
    TaskExecutionStatus,
    TaskMonitor,
    TaskMonitorState,
    UIEvent,
    build_score_explanations,
    infer_phase,
    normalize_ui_event,
)
from snowl.ui.controls import InteractionController
from snowl.ui.input import StdinInputPump
from snowl.ui.panels import PANEL_TYPES, PanelConfig, PanelLayout, PanelRegistry, PanelSpec, load_panel_config

__all__ = [
    "ConsoleRenderer",
    "LiveConsoleRenderer",
    "InteractionController",
    "StdinInputPump",
    "EventPhase",
    "UIEvent",
    "TaskExecutionStatus",
    "TaskMonitorState",
    "TaskMonitor",
    "ScoreExplanation",
    "infer_phase",
    "normalize_ui_event",
    "build_score_explanations",
    "PANEL_TYPES",
    "PanelSpec",
    "PanelLayout",
    "PanelConfig",
    "PanelRegistry",
    "load_panel_config",
]
