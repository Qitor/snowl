"""CLI sub-modules for snowl.

This package contains the modularized CLI implementation. The main
``snowl.cli`` module re-exports the public API for backward compatibility.
"""

from snowl.cli_modules.util import (
    _auto_open_browser,
    _close_renderer,
    _coerce_positive_int,
    _env_float,
    _expected_web_monitor_cache_key,
    _interrupt_on_sigterm,
    _latest_run_log_path,
    _next_available_port,
    _parse_provider_budgets,
    _port_listening,
    _print_interrupt_log_hint,
    _print_run_bootstrap,
    _project_base_dir,
    _same_project,
    _split_csv,
    _try_free_port_listener,
    _try_stop_monitor_process,
    _wait_for_monitor_ready,
)
from snowl.cli_modules.monitor import (
    _ManagedWebMonitor,
    _maybe_autostart_web_monitor,
    _monitor_health,
)
from snowl.cli_modules.render import _build_renderer

__all__ = [
    # util
    "_auto_open_browser",
    "_close_renderer",
    "_coerce_positive_int",
    "_env_float",
    "_expected_web_monitor_cache_key",
    "_interrupt_on_sigterm",
    "_latest_run_log_path",
    "_next_available_port",
    "_parse_provider_budgets",
    "_port_listening",
    "_print_interrupt_log_hint",
    "_print_run_bootstrap",
    "_project_base_dir",
    "_same_project",
    "_split_csv",
    "_try_free_port_listener",
    "_try_stop_monitor_process",
    "_wait_for_monitor_ready",
    # monitor
    "_ManagedWebMonitor",
    "_maybe_autostart_web_monitor",
    "_monitor_health",
    # render
    "_build_renderer",
]
