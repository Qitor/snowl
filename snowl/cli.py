"""Snowl command line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

from snowl.bench import check_benchmark_conformance, list_benchmarks, run_benchmark
from snowl.eval import run_eval
from snowl.examples_lint import validate_examples_layout
from snowl.ui import InteractionController, LiveConsoleRenderer
from snowl.web.runtime import WebRuntimeError, current_webui_cache_key, ensure_next_build, ensure_next_runtime


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [x.strip() for x in value.split(",") if x.strip()]
    return parts or None


def _project_base_dir(path: str) -> Path:
    p = Path(path).resolve()
    return p if p.is_dir() else p.parent


def _latest_run_log_path(base_dir: Path) -> Path | None:
    runs_dir = base_dir / ".snowl" / "runs"
    if not runs_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for child in runs_dir.iterdir():
        log_path = child / "run.log"
        if child.is_dir() and log_path.exists():
            try:
                mtime = log_path.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, log_path))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _print_interrupt_log_hint(base_dir: Path) -> None:
    log_path = _latest_run_log_path(base_dir)
    print("Interrupted by user.")
    if log_path is not None:
        print(f"log={log_path}")
    else:
        print(f"log_dir={base_dir / '.snowl' / 'runs'}")


def _close_renderer(renderer: object | None) -> None:
    if renderer is None:
        return
    close = getattr(renderer, "close", None)
    if callable(close):
        try:
            close()
            return
        except Exception:
            pass
    # Fallback for LiveConsoleRenderer internals to ensure rich alt-screen is released.
    rich_live = getattr(renderer, "_rich_live", None)
    if rich_live is not None:
        try:
            rich_live.stop()
        except Exception:
            pass


def _port_listening(host: str, port: int, *, timeout_sec: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=float(timeout_sec)):
            return True
    except Exception:
        return False


def _monitor_health(host: str, port: int, *, timeout_sec: float = 0.35) -> dict[str, object] | None:
    url = f"http://{host}:{int(port)}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=float(timeout_sec)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _same_project(lhs: str, rhs: str) -> bool:
    try:
        return Path(lhs).resolve() == Path(rhs).resolve()
    except Exception:
        return str(lhs).strip() == str(rhs).strip()


def _coerce_positive_int(value: object | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _expected_web_monitor_cache_key() -> str | None:
    try:
        return current_webui_cache_key()
    except Exception:
        return None


def _try_stop_monitor_process(*, pid: int | None, host: str, port: int, timeout_sec: float = 2.0) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(int(pid), signal.SIGTERM)
    except Exception:
        return False
    deadline = time.time() + float(timeout_sec)
    while time.time() < deadline:
        if not _port_listening(host, port, timeout_sec=0.1):
            return True
        time.sleep(0.1)
    return not _port_listening(host, port, timeout_sec=0.1)


def _try_free_port_listener(*, host: str, port: int, timeout_sec: float = 2.0) -> bool:
    if not _port_listening(host, port, timeout_sec=0.1):
        return True
    pids: list[int] = []
    if os.name == "nt":
        return False
    try:
        done = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-t"],
            check=False,
            capture_output=True,
            text=True,
        )
        for line in (done.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pid = int(line)
            except Exception:
                continue
            if pid > 0 and pid not in pids:
                pids.append(pid)
    except Exception:
        return False
    if not pids:
        return False
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            continue
    deadline = time.time() + float(timeout_sec)
    while time.time() < deadline:
        if not _port_listening(host, port, timeout_sec=0.1):
            return True
        time.sleep(0.1)
    return not _port_listening(host, port, timeout_sec=0.1)


def _next_available_port(host: str, start_port: int, *, max_tries: int = 32) -> int | None:
    base = int(start_port)
    for delta in range(max_tries):
        candidate = base + delta
        if not _port_listening(host, candidate, timeout_sec=0.1):
            return candidate
    return None


def _maybe_autostart_web_monitor(
    *,
    project: str,
    host: str,
    port: int,
    poll_interval_sec: float,
    enabled: bool,
) -> None:
    if not enabled:
        return
    if os.getenv("SNOWL_AUTO_WEB_BOOTSTRAP", "1").lower() in {"0", "false", "off", "no"}:
        return
    if not sys.stdout.isatty():
        return
    requested_project = str(Path(project).resolve())
    expected_cache_key = _expected_web_monitor_cache_key()
    target_port = int(port)
    if _port_listening(host, target_port):
        health = _monitor_health(host, target_port)
        existing_project = str((health or {}).get("project_dir") or "").strip()
        monitor_runtime = str((health or {}).get("monitor_runtime") or "").strip().lower()
        is_next_monitor = monitor_runtime == "next"
        existing_cache_key = str((health or {}).get("cache_key") or "").strip()
        existing_pid = _coerce_positive_int((health or {}).get("pid"))
        if existing_project and _same_project(existing_project, requested_project) and is_next_monitor:
            if expected_cache_key and existing_cache_key != expected_cache_key:
                print(
                    f"Web monitor on http://{host}:{target_port} is outdated "
                    f"(running={existing_cache_key or 'unknown'}, expected={expected_cache_key}); refreshing."
                )
                if _try_stop_monitor_process(pid=existing_pid, host=host, port=target_port) or _try_free_port_listener(
                    host=host, port=target_port
                ):
                    pass
                else:
                    fallback = _next_available_port(host, target_port + 1)
                    if fallback is None:
                        print(f"Web monitor port {target_port} is occupied.")
                        return
                    print(f"Starting upgraded Web monitor on http://{host}:{fallback}")
                    target_port = int(fallback)
            else:
                print(f"Web monitor: http://{host}:{target_port}")
                return
        if _port_listening(host, target_port, timeout_sec=0.1):
            fallback = _next_available_port(host, target_port + 1)
            if fallback is None:
                if existing_project:
                    print(
                        f"Web monitor already running for {existing_project} at http://{host}:{target_port}"
                    )
                else:
                    print(f"Web monitor port {target_port} is occupied.")
                return
            if existing_project:
                if _same_project(existing_project, requested_project) and (not is_next_monitor):
                    print(
                        f"Web monitor port {target_port} is serving legacy/unknown monitor for {existing_project}; "
                        f"starting Next monitor on http://{host}:{fallback}"
                    )
                else:
                    print(
                        f"Web monitor port {target_port} is bound to {existing_project}; "
                        f"starting monitor for {requested_project} on http://{host}:{fallback}"
                    )
            else:
                print(
                    f"Web monitor port {target_port} is occupied by another process; "
                    f"starting monitor for {requested_project} on http://{host}:{fallback}"
                )
            target_port = int(fallback)

    cmd = [
        sys.executable,
        "-m",
        "snowl.cli",
        "web",
        "monitor",
        "--project",
        str(Path(project).resolve()),
        "--host",
        str(host),
        "--port",
        str(target_port),
        "--poll-interval-sec",
        str(float(poll_interval_sec)),
    ]
    env = dict(os.environ)
    env["SNOWL_AUTO_WEB_BOOTSTRAP"] = "0"
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
    except Exception:
        return

    deadline = time.time() + 2.5
    print(f"Web monitor (starting): http://{host}:{target_port}")
    while time.time() < deadline:
        if _port_listening(host, target_port, timeout_sec=0.15):
            print(f"Web monitor: http://{host}:{target_port}")
            return
        time.sleep(0.1)
    print(
        f"Web monitor bootstrap is taking longer than expected on port {target_port}. "
        f"Keep http://{host}:{target_port} open and retry in a few seconds; first bootstrap may take minutes. "
        f"If it still fails, run: snowl web monitor --project {requested_project} --host {host} --port {target_port}"
    )


def _cmd_eval(
    path: str,
    *,
    task: str | None,
    agent: str | None,
    variant: str | None,
    no_ui: bool,
    resume: bool,
    rerun_failed_only: bool,
    checkpoint_key: str | None,
    keys: str | None,
    max_trials: int | None,
    max_sandboxes: int | None,
    max_builds: int | None,
    max_model_calls: int | None,
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
    _maybe_autostart_web_monitor(
        project=str(_project_base_dir(path)),
        host=web_monitor_host,
        port=int(web_monitor_port),
        poll_interval_sec=float(web_monitor_poll_interval_sec),
        enabled=bool(web_monitor),
    )
    effective_no_ui = bool(no_ui or (not cli_ui))
    renderer = None
    if not effective_no_ui:
        renderer = LiveConsoleRenderer(
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
    controller = InteractionController(theme_mode=(ui_theme or "research"))
    if keys:
        tokens = [tok.strip() for tok in keys.replace(";", ",").split(",") if tok.strip()]
        if len(tokens) == 1 and "=" not in tokens[0] and " " not in tokens[0]:
            tokens = list(tokens[0])
        controller.queued_inputs = tokens
    try:
        result = asyncio.run(
            run_eval(
                path,
                task_filter=_split_csv(task),
                agent_filter=_split_csv(agent),
                variant_filter=_split_csv(variant),
                renderer=renderer,
                resume=resume,
                rerun_failed_only=rerun_failed_only,
                checkpoint_key=checkpoint_key,
                interaction_controller=controller,
                max_trials=max_trials,
                max_sandboxes=max_sandboxes,
                max_builds=max_builds,
                max_model_calls=max_model_calls,
                experiment_id=experiment_id,
            )
        )
    except KeyboardInterrupt:
        _close_renderer(renderer)
        _print_interrupt_log_hint(_project_base_dir(path))
        return 130

    if effective_no_ui:
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
    adapter_arg: list[str] | None,
    benchmark_filter: list[str] | None,
    task: str | None,
    agent: str | None,
    variant: str | None,
    no_ui: bool,
    max_trials: int | None,
    max_sandboxes: int | None,
    max_builds: int | None,
    max_model_calls: int | None,
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
    _maybe_autostart_web_monitor(
        project=str(_project_base_dir(project)),
        host=web_monitor_host,
        port=int(web_monitor_port),
        poll_interval_sec=float(web_monitor_poll_interval_sec),
        enabled=bool(web_monitor),
    )
    effective_no_ui = bool(no_ui or (not cli_ui))
    renderer = None
    if not effective_no_ui:
        renderer = LiveConsoleRenderer(
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
    try:
        result = asyncio.run(
            run_benchmark(
                benchmark,
                project_path=project,
                split=split,
                limit=limit,
                benchmark_args=adapter_arg,
                benchmark_filters=benchmark_filter,
                task_filter=_split_csv(task),
                agent_filter=_split_csv(agent),
                variant_filter=_split_csv(variant),
                renderer=renderer,
                max_trials=max_trials,
                max_sandboxes=max_sandboxes,
                max_builds=max_builds,
                max_model_calls=max_model_calls,
                experiment_id=experiment_id,
            )
        )
    except KeyboardInterrupt:
        _close_renderer(renderer)
        _print_interrupt_log_hint(_project_base_dir(project))
        return 130
    if effective_no_ui:
        return _print_summary(result)
    return 0 if result.summary.error == 0 else 1


def _cmd_bench_check(benchmark: str, *, adapter_arg: list[str] | None) -> int:
    report = check_benchmark_conformance(benchmark, benchmark_args=adapter_arg)
    print(f"ok={report['ok']}")
    for check in report["checks"]:
        print(f"- {check['name']}: {check['ok']}")
    return 0 if report["ok"] else 1


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


def _cmd_web_monitor(
    *,
    project: str,
    host: str,
    port: int,
    poll_interval_sec: float,
) -> int:
    env = dict(os.environ)
    resolved_project = str(Path(project).resolve())
    env["SNOWL_PROJECT_DIR"] = resolved_project
    env["SNOWL_POLL_INTERVAL_SEC"] = str(float(poll_interval_sec))
    dev_mode = os.getenv("SNOWL_WEB_DEV", "0").lower() in {"1", "true", "on", "yes"}
    cmd = [
        "npm",
        "run",
        ("dev" if dev_mode else "start"),
        "--",
        "--hostname",
        str(host),
        "--port",
        str(int(port)),
    ]
    try:
        print("[web] ensure deps")
        runtime = ensure_next_runtime(log=print)
        env["SNOWL_WEB_CACHE_KEY"] = runtime.cache_key
        env["SNOWL_WEB_SOURCE_DIR"] = str(runtime.source_dir)
        env["SNOWL_WEB_SOURCE_MODE"] = runtime.source_mode
        monitor_cfg_path = runtime.app_dir / ".snowl-monitor.json"
        monitor_cfg_path.write_text(
            json.dumps(
                {
                    "project_dir": resolved_project,
                    "poll_interval_sec": float(poll_interval_sec),
                    "cache_key": runtime.cache_key,
                    "source_dir": str(runtime.source_dir),
                    "source_mode": runtime.source_mode,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if dev_mode:
            print("[web] ensure build: skipped (SNOWL_WEB_DEV=1)")
        else:
            print("[web] ensure build")
            ensure_next_build(runtime, log=print)
        print("[web] start server")
        print(f"Web monitor: http://{host}:{int(port)}")
        completed = subprocess.run(
            cmd,
            cwd=str(runtime.app_dir),
            env=env,
            check=False,
        )
        return int(completed.returncode)
    except KeyboardInterrupt:
        return 130
    except WebRuntimeError as exc:
        print(f"Web monitor bootstrap failed: {exc}")
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"Web monitor bootstrap failed: command exited with status {exc.returncode}: {' '.join(exc.cmd)}")
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snowl")
    sub = parser.add_subparsers(dest="command", required=True)

    eval_parser = sub.add_parser("eval", help="Run evaluation with auto-discovery.")
    eval_parser.add_argument("path", nargs="?", default=".", help="Project path")
    eval_parser.add_argument("--task", dest="task", default=None, help="Task id selector (csv).")
    eval_parser.add_argument("--agent", dest="agent", default=None, help="Agent id selector (csv).")
    eval_parser.add_argument("--variant", dest="variant", default=None, help="Variant id selector (csv).")
    eval_parser.add_argument(
        "--cli-ui",
        action="store_true",
        help="Enable legacy live CLI renderer (default uses Web UI + terminal summary).",
    )
    eval_parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Disable legacy live CLI renderer (compat flag; default already disabled).",
    )
    eval_parser.add_argument("--resume", action="store_true", help="Resume from checkpoint.")
    eval_parser.add_argument(
        "--rerun-failed-only",
        action="store_true",
        help="Run only failed trials from the latest run.",
    )
    eval_parser.add_argument("--checkpoint-key", default=None, help="Checkpoint key override.")
    eval_parser.add_argument(
        "--keys",
        default=None,
        help="Simulated interactive key sequence (e.g. 'pfar') for automation/tests.",
    )
    eval_parser.add_argument("--max-trials", type=int, default=None, help="Max concurrent trials.")
    eval_parser.add_argument("--max-sandboxes", type=int, default=None, help="Max concurrent sandboxes.")
    eval_parser.add_argument("--max-builds", type=int, default=None, help="Max concurrent container builds.")
    eval_parser.add_argument("--max-model-calls", type=int, default=None, help="Max concurrent model API calls.")
    eval_parser.add_argument(
        "--experiment-id",
        default=None,
        help="Optional experiment id for cross-run aggregation.",
    )
    eval_parser.add_argument(
        "--no-web-monitor",
        action="store_true",
        help="Disable auto-start of the web monitor during eval.",
    )
    eval_parser.add_argument("--web-monitor-host", default="127.0.0.1", help="Web monitor host.")
    eval_parser.add_argument("--web-monitor-port", type=int, default=8765, help="Web monitor port.")
    eval_parser.add_argument(
        "--web-monitor-poll-interval-sec",
        type=float,
        default=0.5,
        help="Web monitor poll interval for run discovery.",
    )
    eval_parser.add_argument("--ui-refresh-ms", type=int, default=None, help="UI refresh interval in milliseconds.")
    eval_parser.add_argument("--ui-max-events", type=int, default=None, help="UI event buffer max entries.")
    eval_parser.add_argument("--ui-max-failures", type=int, default=None, help="UI failure buffer max entries.")
    eval_parser.add_argument("--ui-max-active-trials", type=int, default=None, help="UI active trial buffer max entries.")
    eval_parser.add_argument(
        "--ui-refresh-profile",
        choices=["smooth", "balanced", "low_cpu"],
        default=None,
        help="UI refresh profile.",
    )
    eval_parser.add_argument(
        "--ui-theme",
        choices=["contrast", "quiet", "research", "research_redops"],
        default="research",
        help="UI theme mode.",
    )
    eval_parser.add_argument(
        "--ui-mode",
        choices=["auto", "default", "qa_dense", "ops_dense", "compare_dense"],
        default=None,
        help="UI panel mode preset.",
    )
    eval_parser.add_argument("--ui-no-banner", action="store_true", help="Start with banner collapsed.")

    bench_parser = sub.add_parser("bench", help="Benchmark adapter commands.")
    bench_sub = bench_parser.add_subparsers(dest="bench_command", required=True)

    bench_list = bench_sub.add_parser("list", help="List available benchmark adapters.")

    bench_run = bench_sub.add_parser("run", help="Run benchmark tasks with local agent/scorer.")
    bench_run.add_argument("benchmark", help="Benchmark adapter name.")
    bench_run.add_argument("--project", default=".", help="Project path with agent.py/scorer.py/tool.py.")
    bench_run.add_argument("--split", default="test", help="Benchmark split.")
    bench_run.add_argument("--limit", type=int, default=None, help="Max benchmark samples to load.")
    bench_run.add_argument(
        "--adapter-arg",
        action="append",
        default=None,
        help="Adapter arg key=value (repeatable).",
    )
    bench_run.add_argument(
        "--benchmark-filter",
        action="append",
        default=None,
        help="Benchmark row filter key=value (repeatable).",
    )
    bench_run.add_argument("--task", dest="task", default=None, help="Task id selector (csv).")
    bench_run.add_argument("--agent", dest="agent", default=None, help="Agent id selector (csv).")
    bench_run.add_argument("--variant", dest="variant", default=None, help="Variant id selector (csv).")
    bench_run.add_argument(
        "--cli-ui",
        action="store_true",
        help="Enable legacy live CLI renderer (default uses Web UI + terminal summary).",
    )
    bench_run.add_argument(
        "--no-ui",
        action="store_true",
        help="Disable legacy live CLI renderer (compat flag; default already disabled).",
    )
    bench_run.add_argument("--max-trials", type=int, default=None, help="Max concurrent trials.")
    bench_run.add_argument("--max-sandboxes", type=int, default=None, help="Max concurrent sandboxes.")
    bench_run.add_argument("--max-builds", type=int, default=None, help="Max concurrent container builds.")
    bench_run.add_argument("--max-model-calls", type=int, default=None, help="Max concurrent model API calls.")
    bench_run.add_argument(
        "--experiment-id",
        default=None,
        help="Optional experiment id for cross-run aggregation.",
    )
    bench_run.add_argument(
        "--no-web-monitor",
        action="store_true",
        help="Disable auto-start of the web monitor during benchmark runs.",
    )
    bench_run.add_argument("--web-monitor-host", default="127.0.0.1", help="Web monitor host.")
    bench_run.add_argument("--web-monitor-port", type=int, default=8765, help="Web monitor port.")
    bench_run.add_argument(
        "--web-monitor-poll-interval-sec",
        type=float,
        default=0.5,
        help="Web monitor poll interval for run discovery.",
    )
    bench_run.add_argument("--ui-refresh-ms", type=int, default=None, help="UI refresh interval in milliseconds.")
    bench_run.add_argument("--ui-max-events", type=int, default=None, help="UI event buffer max entries.")
    bench_run.add_argument("--ui-max-failures", type=int, default=None, help="UI failure buffer max entries.")
    bench_run.add_argument("--ui-max-active-trials", type=int, default=None, help="UI active trial buffer max entries.")
    bench_run.add_argument(
        "--ui-refresh-profile",
        choices=["smooth", "balanced", "low_cpu"],
        default=None,
        help="UI refresh profile.",
    )
    bench_run.add_argument(
        "--ui-theme",
        choices=["contrast", "quiet", "research", "research_redops"],
        default="research",
        help="UI theme mode.",
    )
    bench_run.add_argument(
        "--ui-mode",
        choices=["auto", "default", "qa_dense", "ops_dense", "compare_dense"],
        default=None,
        help="UI panel mode preset.",
    )
    bench_run.add_argument("--ui-no-banner", action="store_true", help="Start with banner collapsed.")

    bench_check = bench_sub.add_parser("check", help="Run benchmark adapter conformance checks.")
    bench_check.add_argument("benchmark", help="Benchmark adapter name.")
    bench_check.add_argument(
        "--adapter-arg",
        action="append",
        default=None,
        help="Adapter arg key=value (repeatable).",
    )

    examples_parser = sub.add_parser("examples", help="Examples validation commands.")
    examples_sub = examples_parser.add_subparsers(dest="examples_command", required=True)
    examples_check = examples_sub.add_parser("check", help="Validate examples folder layout.")
    examples_check.add_argument("path", nargs="?", default="examples", help="Examples root path.")

    web_parser = sub.add_parser("web", help="Web monitor commands.")
    web_sub = web_parser.add_subparsers(dest="web_command", required=True)
    web_monitor = web_sub.add_parser("monitor", help="Start local web monitor (SSE).")
    web_monitor.add_argument("--project", default=".", help="Project root path.")
    web_monitor.add_argument("--host", default="127.0.0.1", help="Bind host.")
    web_monitor.add_argument("--port", type=int, default=8765, help="Bind port.")
    web_monitor.add_argument(
        "--poll-interval-sec",
        type=float,
        default=0.5,
        help="Background run discovery poll interval.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "eval":
        return _cmd_eval(
            str(Path(args.path)),
            task=args.task,
            agent=args.agent,
            variant=args.variant,
            no_ui=args.no_ui,
            resume=args.resume,
            rerun_failed_only=args.rerun_failed_only,
            checkpoint_key=args.checkpoint_key,
            keys=args.keys,
            max_trials=args.max_trials,
            max_sandboxes=args.max_sandboxes,
            max_builds=args.max_builds,
            max_model_calls=args.max_model_calls,
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

    if args.command == "bench":
        if args.bench_command == "list":
            return _cmd_bench_list()
        if args.bench_command == "run":
            return _cmd_bench_run(
                args.benchmark,
                project=str(Path(args.project)),
                split=args.split,
                limit=args.limit,
                adapter_arg=args.adapter_arg,
                benchmark_filter=args.benchmark_filter,
                task=args.task,
                agent=args.agent,
                variant=args.variant,
                no_ui=args.no_ui,
                max_trials=args.max_trials,
                max_sandboxes=args.max_sandboxes,
                max_builds=args.max_builds,
                max_model_calls=args.max_model_calls,
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
        if args.bench_command == "check":
            return _cmd_bench_check(args.benchmark, adapter_arg=args.adapter_arg)

    if args.command == "examples":
        if args.examples_command == "check":
            return _cmd_examples_check(str(Path(args.path)))

    if args.command == "web":
        if args.web_command == "monitor":
            return _cmd_web_monitor(
                project=str(Path(args.project)),
                host=str(args.host),
                port=int(args.port),
                poll_interval_sec=float(args.poll_interval_sec),
            )

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
