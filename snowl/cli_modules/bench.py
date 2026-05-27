"""Benchmark, suite, and examples command implementations."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from snowl.bench import check_benchmark_conformance, list_benchmarks, run_benchmark, scaffold_benchmark
from snowl.eval import EvalRunBootstrap
from snowl.examples_lint import validate_examples_layout
from snowl.suite import check_suite_config, run_suite
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
from snowl.cli_modules.eval import _print_summary


def _cmd_bench_list() -> int:
    entries = list_benchmarks()
    for item in entries:
        print(f"{item['name']}: {item['description']}")
    return 0


def _cmd_bench_run(
    benchmark: str,
    *,
    project: str,
    split: str,
    limit: int | None,
    adapter: str | None,
    adapter_arg: list[str] | None,
    benchmark_filter: list[str] | None,
    task: str | None,
    agent: str | None,
    variant: str | None,
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
    if not cli_ui and not no_ui:
        print(f"Snowl Benchmark Run: project={project_dir}")
        print(
            "Snowl Benchmark Run: benchmark={benchmark} split={split} task_filter={task} agent_filter={agent} variant_filter={variant}".format(
                benchmark=benchmark,
                split=split,
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
            _print_run_bootstrap("Snowl Benchmark Run", info)
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
                run_benchmark(
                    benchmark,
                    project_path=project,
                    split=split,
                    limit=limit,
                    adapter_spec=adapter,
                    benchmark_args=adapter_arg,
                    benchmark_filters=benchmark_filter,
                    task_filter=_split_csv(task),
                    agent_filter=_split_csv(agent),
                    variant_filter=_split_csv(variant),
                    renderer=renderer,
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


def _cmd_bench_check(benchmark: str, *, adapter: str | None, adapter_arg: list[str] | None) -> int:
    report = check_benchmark_conformance(benchmark, adapter_spec=adapter, benchmark_args=adapter_arg)
    print(f"ok={report['ok']}")
    for check in report["checks"]:
        print(f"- {check['name']}: {check['ok']}")
    return 0 if report["ok"] else 1


def _cmd_bench_scaffold(name: str, *, out: str) -> int:
    target = scaffold_benchmark(name, out_dir=out)
    print(f"created={target}")
    print(f"check=snowl bench check {name} --adapter {target / 'adapter.py'}:adapter --adapter-arg dataset_path={target / 'data.jsonl'}")
    return 0


def _cmd_suite_check(path: str) -> int:
    report = check_suite_config(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


def _cmd_suite_run(path: str) -> int:
    result = asyncio.run(run_suite(path))
    print(f"suite_run_id={result.suite_run_id}")
    print(f"summary={result.summary_path}")
    return 0 if result.status != "failed" else 1


def _cmd_examples_check(path: str) -> int:
    report = validate_examples_layout(path)
    print(f"ok={report.ok}")
    for check in report.checks:
        name = check.get("name")
        ok = check.get("ok")
        example = check.get("example")
        msg = check.get("message") or ""
        prefix = f"[{example}] " if example else ""
        print(f"- {prefix}{name}: {ok}" + (f" ({msg})" if msg else ""))
    return 0 if report.ok else 1
