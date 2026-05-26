"""Command implementations for eval and retry subcommands."""

from __future__ import annotations

import asyncio
from pathlib import Path

from snowl.eval import EvalRunBootstrap, retry_run, run_eval
from snowl.ui import InteractionController

from snowl.cli_modules.util import (
    _auto_open_browser,
    _close_renderer,
    _interrupt_on_sigterm,
    _parse_provider_budgets,
    _print_interrupt_log_hint,
    _print_run_bootstrap,
    _project_base_dir,
    _split_csv,
)
from snowl.cli_modules.monitor import _ManagedWebMonitor
from snowl.cli_modules.render import _build_renderer


def _cmd_eval(
    path: str,
    *,
    task: str | None,
    agent: str | None,
    variant: str | None,
    scorer: str | None,
    no_ui: bool,
    resume: bool,
    rerun_failed_only: bool,
    checkpoint_key: str | None,
    keys: str | None,
    max_running_trials: int | None,
    max_container_slots: int | None,
    max_builds: int | None,
    max_scoring_tasks: int | None,
    provider_budget: list[str] | None,
    keep_containers: bool,
    keep_failed_containers: bool,
    ui_refresh_ms: int | None,
    ui_max_events: int | None,
    ui_max_failures: int | None,
    ui_max_active_trials: int | None,
    ui_refresh_profile: str | None,
    ui_theme: str | None,
    ui_mode: str | None,
    ui_no_banner: bool,
    experiment_id: str | None,
    web_monitor: bool,
    web_monitor_host: str,
    web_monitor_port: int,
    web_monitor_poll_interval_sec: float,
    cli_ui: bool,
) -> int:
    project_dir = _project_base_dir(path)
    renderer = _build_renderer(
        no_ui=bool(no_ui),
        cli_ui=bool(cli_ui),
        ui_refresh_ms=ui_refresh_ms,
        ui_max_events=ui_max_events,
        ui_max_failures=ui_max_failures,
        ui_max_active_trials=ui_max_active_trials,
        ui_refresh_profile=ui_refresh_profile,
        ui_theme=ui_theme,
        ui_mode=ui_mode,
        ui_no_banner=ui_no_banner,
    )
    controller = InteractionController(theme_mode=(ui_theme or "research"))
    if keys:
        tokens = [tok.strip() for tok in keys.replace(";", ",").split(",") if tok.strip()]
        if len(tokens) == 1 and "=" not in tokens[0] and " " not in tokens[0]:
            tokens = list(tokens[0])
        controller.queued_inputs = tokens
    if not cli_ui and not no_ui:
        print(f"Snowl Eval: project={project_dir}")
        print(
            "Snowl Eval: example={example} task_filter={task} agent_filter={agent} variant_filter={variant}".format(
                example=project_dir.name,
                task=(task or "*"),
                agent=(agent or "*"),
                variant=(variant or "*"),
            )
        )
    monitor = _ManagedWebMonitor(
        project=str(project_dir),
        host=web_monitor_host,
        port=int(web_monitor_port),
        poll_interval_sec=float(web_monitor_poll_interval_sec),
        enabled=bool(web_monitor),
    )
    sidecar_started = {"done": False}

    def _on_run_bootstrap(info: EvalRunBootstrap) -> None:
        if not cli_ui and not no_ui:
            _print_run_bootstrap("Snowl Eval", info)
        if sidecar_started["done"]:
            return
        sidecar_started["done"] = True
        url = monitor.maybe_start()
        if url:
            print(f"Web monitor: {url}")
            _auto_open_browser(url)

    try:
        with _interrupt_on_sigterm():
            result = asyncio.run(
                run_eval(
                    path,
                    task_filter=_split_csv(task),
                    agent_filter=_split_csv(agent),
                    variant_filter=_split_csv(variant),
                    scorer_filter=_split_csv(scorer),
                    renderer=renderer,
                    resume=resume,
                    rerun_failed_only=rerun_failed_only,
                    checkpoint_key=checkpoint_key,
                    interaction_controller=controller,
                    max_running_trials=max_running_trials,
                    max_container_slots=max_container_slots,
                    max_builds=max_builds,
                    max_scoring_tasks=max_scoring_tasks,
                    provider_budgets=_parse_provider_budgets(provider_budget),
                    keep_containers=keep_containers,
                    keep_failed_containers=keep_failed_containers,
                    experiment_id=experiment_id,
                    on_run_bootstrap=_on_run_bootstrap,
                )
            )
    except KeyboardInterrupt:
        _close_renderer(renderer)
        monitor.stop()
        _print_interrupt_log_hint(project_dir)
        return 130
    finally:
        monitor.stop()

    if renderer is None:
        summary = result.summary
        print(
            "Snowl Eval Summary: total={total} success={success} incorrect={incorrect} "
            "error={error} limit_exceeded={limit} cancelled={cancelled}".format(
                total=summary.total,
                success=summary.success,
                incorrect=summary.incorrect,
                error=summary.error,
                limit=summary.limit_exceeded,
                cancelled=summary.cancelled,
            )
        )
        print(f"artifacts={result.artifacts_dir}")
        print(f"log={result.artifacts_dir}/run.log")
        print(f"rerun={result.rerun_command}")

    return 0 if result.summary.error == 0 else 1


def _cmd_retry(
    run_id: str,
    *,
    project: str,
    no_ui: bool,
    max_running_trials: int | None,
    max_container_slots: int | None,
    max_builds: int | None,
    max_scoring_tasks: int | None,
    provider_budget: list[str] | None,
    keep_containers: bool,
    keep_failed_containers: bool,
    ui_refresh_ms: int | None,
    ui_max_events: int | None,
    ui_max_failures: int | None,
    ui_max_active_trials: int | None,
    ui_refresh_profile: str | None,
    ui_theme: str | None,
    ui_mode: str | None,
    ui_no_banner: bool,
    experiment_id: str | None,
    web_monitor: bool,
    web_monitor_host: str,
    web_monitor_port: int,
    web_monitor_poll_interval_sec: float,
    cli_ui: bool,
) -> int:
    project_dir = _project_base_dir(project)
    renderer = _build_renderer(
        no_ui=bool(no_ui),
        cli_ui=bool(cli_ui),
        ui_refresh_ms=ui_refresh_ms,
        ui_max_events=ui_max_events,
        ui_max_failures=ui_max_failures,
        ui_max_active_trials=ui_max_active_trials,
        ui_refresh_profile=ui_refresh_profile,
        ui_theme=ui_theme,
        ui_mode=ui_mode,
        ui_no_banner=ui_no_banner,
    )
    controller = InteractionController(theme_mode=(ui_theme or "research"))
    if not cli_ui and not no_ui:
        print(f"Snowl Retry: run_id={run_id}")
        print(f"Snowl Retry: project={project_dir}")
    monitor = _ManagedWebMonitor(
        project=str(project_dir),
        host=web_monitor_host,
        port=int(web_monitor_port),
        poll_interval_sec=float(web_monitor_poll_interval_sec),
        enabled=bool(web_monitor),
    )
    sidecar_started = {"done": False}

    def _on_run_bootstrap(info: EvalRunBootstrap) -> None:
        if not cli_ui and not no_ui:
            _print_run_bootstrap("Snowl Retry", info)
        if sidecar_started["done"]:
            return
        sidecar_started["done"] = True
        url = monitor.maybe_start()
        if url:
            print(f"Web monitor: {url}")
            _auto_open_browser(url)

    try:
        with _interrupt_on_sigterm():
            result = asyncio.run(
                retry_run(
                    run_id,
                    project_path=project,
                    renderer=renderer,
                    interaction_controller=controller,
                    max_running_trials=max_running_trials,
                    max_container_slots=max_container_slots,
                    max_builds=max_builds,
                    max_scoring_tasks=max_scoring_tasks,
                    provider_budgets=_parse_provider_budgets(provider_budget),
                    keep_containers=keep_containers,
                    keep_failed_containers=keep_failed_containers,
                    experiment_id=experiment_id,
                    on_run_bootstrap=_on_run_bootstrap,
                )
            )
    except KeyboardInterrupt:
        _close_renderer(renderer)
        monitor.stop()
        _print_interrupt_log_hint(project_dir)
        return 130
    finally:
        monitor.stop()

    if renderer is None:
        return _print_summary(result)
    return 0 if result.summary.error == 0 else 1


def _print_summary(result) -> int:
    summary = result.summary
    print(
        "Snowl Eval Summary: total={total} success={success} incorrect={incorrect} "
        "error={error} limit_exceeded={limit} cancelled={cancelled}".format(
            total=summary.total,
            success=summary.success,
            incorrect=summary.incorrect,
            error=summary.error,
            limit=summary.limit_exceeded,
            cancelled=summary.cancelled,
        )
    )
    print(f"artifacts={result.artifacts_dir}")
    print(f"log={result.artifacts_dir}/run.log")
    print(f"rerun={result.rerun_command}")
    return 0 if summary.error == 0 else 1
