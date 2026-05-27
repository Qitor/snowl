"""Benchmark sub-command parser."""

from __future__ import annotations

import argparse

from snowl.cli_modules.parsers.eval_parser import _add_ui_flags, _add_runtime_flags, _add_web_monitor_flags


def add_bench_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("bench", help="Benchmark adapter commands.")
    bench_sub = parser.add_subparsers(dest="bench_command", required=True)

    bench_list = bench_sub.add_parser("list", help="List available benchmark adapters.")

    bench_run = bench_sub.add_parser("run", help="Run benchmark tasks with local agent/scorer.")
    bench_run.add_argument("benchmark", help="Benchmark adapter name.")
    bench_run.add_argument("--project", default="project.yml", help="Path to project.yml.")
    bench_run.add_argument("--split", default="test", help="Benchmark split.")
    bench_run.add_argument("--limit", type=int, default=None, help="Max benchmark samples to load.")
    bench_run.add_argument("--adapter", default=None, help="External adapter spec in module.py:object format.")
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
    _add_ui_flags(bench_run)
    _add_runtime_flags(bench_run)
    _add_web_monitor_flags(bench_run)

    bench_check = bench_sub.add_parser("check", help="Run benchmark adapter conformance checks.")
    bench_check.add_argument("benchmark", help="Benchmark adapter name.")
    bench_check.add_argument("--adapter", default=None, help="External adapter spec in module.py:object format.")
    bench_check.add_argument(
        "--adapter-arg",
        action="append",
        default=None,
        help="Adapter arg key=value (repeatable).",
    )

    bench_scaffold = bench_sub.add_parser("scaffold", help="Create a third-party benchmark adapter template.")
    bench_scaffold.add_argument("name", help="Benchmark name for the scaffold.")
    bench_scaffold.add_argument("--out", required=True, help="Output directory for scaffold files.")

    return parser
