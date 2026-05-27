"""Top-level operator CLI entrypoint that wires commands into eval, bench, retry, and monitor flows.

Framework role:
- Owns user-facing command UX, flag parsing, process lifecycle, and web monitor bootstrap behavior.

Runtime/usage wiring:
- Delegates domain logic into lower layers (`snowl.eval`, `snowl.bench`, `snowl.web.*`).
- Command implementations are in ``snowl.cli_modules`` sub-package.

Change guardrails:
- Keep business/runtime semantics in lower layers; this file should orchestrate, not re-implement.
"""

from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from snowl.cli_modules.parsers import build_parser

# Backward-compat re-exports for test monkeypatching.
# Tests patch these symbols on the ``snowl.cli`` module directly.
from snowl.cli_modules.util import (  # noqa: F401
    _close_renderer,
    _expected_web_monitor_cache_key,
    _next_available_port,
    _port_listening,
    _try_free_port_listener,
    _try_stop_monitor_process,
)
from snowl.cli_modules.monitor import (  # noqa: F401
    _ManagedWebMonitor,
    _maybe_autostart_web_monitor,
    _monitor_health,
)
from snowl.eval import run_eval  # noqa: F401
from snowl.web.runtime import ensure_next_build, ensure_next_runtime  # noqa: F401


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    command = args.command

    if command == "eval":
        from snowl.cli_modules.eval import _cmd_eval
        return _cmd_eval(
            str(Path(args.path)),
            task=args.task,
            agent=args.agent,
            variant=args.variant,
            scorer=args.scorer,
            no_ui=args.no_ui,
            resume=args.resume,
            rerun_failed_only=args.rerun_failed_only,
            checkpoint_key=args.checkpoint_key,
            keys=args.keys,
            max_running_trials=args.max_running_trials,
            max_container_slots=args.max_container_slots,
            max_builds=args.max_builds,
            max_scoring_tasks=args.max_scoring_tasks,
            provider_budget=args.provider_budget,
            keep_containers=bool(args.keep_containers),
            keep_failed_containers=bool(args.keep_failed_containers),
            ui_refresh_ms=args.ui_refresh_ms,
            ui_max_events=args.ui_max_events,
            ui_max_failures=args.ui_max_failures,
            ui_max_active_trials=args.ui_max_active_trials,
            ui_refresh_profile=args.ui_refresh_profile,
            ui_theme=args.ui_theme,
            ui_mode=args.ui_mode,
            ui_no_banner=args.ui_no_banner,
            experiment_id=args.experiment_id,
            web_monitor=(not args.no_web_monitor),
            web_monitor_host=args.web_monitor_host,
            web_monitor_port=args.web_monitor_port,
            web_monitor_poll_interval_sec=args.web_monitor_poll_interval_sec,
            cli_ui=bool(args.cli_ui),
        )

    if command == "retry":
        from snowl.cli_modules.eval import _cmd_retry
        return _cmd_retry(
            str(args.run_id),
            project=str(Path(args.project)),
            no_ui=args.no_ui,
            max_running_trials=args.max_running_trials,
            max_container_slots=args.max_container_slots,
            max_builds=args.max_builds,
            max_scoring_tasks=args.max_scoring_tasks,
            provider_budget=args.provider_budget,
            keep_containers=bool(args.keep_containers),
            keep_failed_containers=bool(args.keep_failed_containers),
            ui_refresh_ms=args.ui_refresh_ms,
            ui_max_events=args.ui_max_events,
            ui_max_failures=args.ui_max_failures,
            ui_max_active_trials=args.ui_max_active_trials,
            ui_refresh_profile=args.ui_refresh_profile,
            ui_theme=args.ui_theme,
            ui_mode=args.ui_mode,
            ui_no_banner=args.ui_no_banner,
            experiment_id=args.experiment_id,
            web_monitor=(not args.no_web_monitor),
            web_monitor_host=args.web_monitor_host,
            web_monitor_port=args.web_monitor_port,
            web_monitor_poll_interval_sec=args.web_monitor_poll_interval_sec,
            cli_ui=bool(args.cli_ui),
        )

    if command == "bench":
        bench_command = args.bench_command
        if bench_command == "list":
            from snowl.cli_modules.bench import _cmd_bench_list
            return _cmd_bench_list()
        if bench_command == "run":
            from snowl.cli_modules.bench import _cmd_bench_run
            return _cmd_bench_run(
                args.benchmark,
                project=str(Path(args.project)),
                split=args.split,
                limit=args.limit,
                adapter=args.adapter,
                adapter_arg=args.adapter_arg,
                benchmark_filter=args.benchmark_filter,
                task=args.task,
                agent=args.agent,
                variant=args.variant,
                no_ui=args.no_ui,
                max_running_trials=args.max_running_trials,
                max_container_slots=args.max_container_slots,
                max_builds=args.max_builds,
                max_scoring_tasks=args.max_scoring_tasks,
                provider_budget=args.provider_budget,
                keep_containers=bool(args.keep_containers),
                keep_failed_containers=bool(args.keep_failed_containers),
                ui_refresh_ms=args.ui_refresh_ms,
                ui_max_events=args.ui_max_events,
                ui_max_failures=args.ui_max_failures,
                ui_max_active_trials=args.ui_max_active_trials,
                ui_refresh_profile=args.ui_refresh_profile,
                ui_theme=args.ui_theme,
                ui_mode=args.ui_mode,
                ui_no_banner=args.ui_no_banner,
                experiment_id=args.experiment_id,
                web_monitor=(not args.no_web_monitor),
                web_monitor_host=args.web_monitor_host,
                web_monitor_port=args.web_monitor_port,
                web_monitor_poll_interval_sec=args.web_monitor_poll_interval_sec,
                cli_ui=bool(args.cli_ui),
            )
        if bench_command == "check":
            from snowl.cli_modules.bench import _cmd_bench_check
            return _cmd_bench_check(args.benchmark, adapter=args.adapter, adapter_arg=args.adapter_arg)
        if bench_command == "scaffold":
            from snowl.cli_modules.bench import _cmd_bench_scaffold
            return _cmd_bench_scaffold(args.name, out=args.out)

    if command == "suite":
        suite_command = args.suite_command
        if suite_command == "check":
            from snowl.cli_modules.bench import _cmd_suite_check
            return _cmd_suite_check(args.path)
        if suite_command == "run":
            from snowl.cli_modules.bench import _cmd_suite_run
            return _cmd_suite_run(args.path)

    if command == "examples":
        if args.examples_command == "check":
            from snowl.cli_modules.bench import _cmd_examples_check
            return _cmd_examples_check(str(Path(args.path)))

    if command == "web":
        if args.web_command == "monitor":
            from snowl.cli_modules.web import _cmd_web_monitor
            return _cmd_web_monitor(
                project=str(Path(args.project)),
                host=str(args.host),
                port=int(args.port),
                poll_interval_sec=float(args.poll_interval_sec),
            )

    if command == "report":
        from snowl.cli_modules.web import _cmd_report
        return _cmd_report(
            args.run_id,
            project=str(Path(args.project)),
            format=args.format,
            output=args.output,
        )

    if command == "compare":
        from snowl.cli_modules.web import _cmd_compare
        return _cmd_compare(
            args.run_id_a,
            args.run_id_b,
            project=str(Path(args.project)),
            format=args.format,
            output=args.output,
        )

    if command == "rescore":
        from snowl.cli_modules.web import _cmd_rescore
        return _cmd_rescore(
            args.run_id,
            project=str(Path(args.project)),
            scorer=args.scorer,
        )

    if command == "export":
        from snowl.cli_modules.web import _cmd_export
        return _cmd_export(
            args.run_id,
            project=str(Path(args.project)),
            format=args.format,
            output=args.output,
            trial_key=args.trial_key,
        )

    if command == "registry":
        registry_command = args.registry_command
        if registry_command == "list":
            from snowl.cli_modules.registry import _cmd_registry_list
            return _cmd_registry_list(kind=args.kind)
        if registry_command == "doctor":
            from snowl.cli_modules.registry import _cmd_registry_doctor
            return _cmd_registry_doctor()
        if registry_command == "info":
            from snowl.cli_modules.registry import _cmd_registry_info
            return _cmd_registry_info(args.name)

    if command == "leaderboard":
        leaderboard_command = args.leaderboard_command
        if leaderboard_command == "publish":
            from snowl.cli_modules.leaderboard import _cmd_leaderboard_publish
            return _cmd_leaderboard_publish(args.run_dir)
        if leaderboard_command == "list":
            from snowl.cli_modules.leaderboard import _cmd_leaderboard_list
            return _cmd_leaderboard_list(domain=args.domain, top=args.top, cost_aware=args.cost_aware)
        if leaderboard_command == "compare":
            from snowl.cli_modules.leaderboard import _cmd_leaderboard_compare
            return _cmd_leaderboard_compare(args.run_dir_a, args.run_dir_b)

    if command == "quick-eval":
        from snowl.cli_modules.quick_eval import _cmd_quick_eval
        return _cmd_quick_eval(
            agent=args.agent,
            benchmark=args.benchmark,
            samples=args.samples,
            scorer=args.scorer,
            limit=args.limit,
            max_tokens=args.max_tokens,
        )

    if command == "check":
        from snowl.cli_modules.check import _cmd_check
        return _cmd_check()

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
