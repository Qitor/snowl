"""Renderer construction for the Snowl CLI."""

from __future__ import annotations

from snowl.ui import ConsoleRenderer, LiveConsoleRenderer


def _build_renderer(
    *,
    no_ui: bool,
    cli_ui: bool,
    ui_refresh_ms: int | None,
    ui_max_events: int | None,
    ui_max_failures: int | None,
    ui_max_active_trials: int | None,
    ui_refresh_profile: str | None,
    ui_theme: str | None,
    ui_mode: str | None,
    ui_no_banner: bool,
):
    if cli_ui:
        return LiveConsoleRenderer(
            verbose=True,
            refresh_interval_ms=(ui_refresh_ms if ui_refresh_ms is not None else 80),
            max_events=(ui_max_events if ui_max_events is not None else 240),
            max_failures=(ui_max_failures if ui_max_failures is not None else 120),
            max_active_trials=(ui_max_active_trials if ui_max_active_trials is not None else 48),
            ui_refresh_profile=(ui_refresh_profile or "balanced"),
            theme_mode=(ui_theme or "research"),
            ui_mode=(ui_mode or "auto"),
            show_banner=(not ui_no_banner),
        )
    if no_ui:
        return None
    return ConsoleRenderer(verbose=True)
