"""Eval sub-command parser."""

from __future__ import annotations

import argparse


def add_eval_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("eval", help="Run evaluation from a project.yml file.")
    parser.add_argument("path", nargs="?", default="project.yml", help="Path to project.yml")
    parser.add_argument("--task", dest="task", default=None, help="Task id selector (csv).")
    parser.add_argument("--agent", dest="agent", default=None, help="Agent id selector (csv).")
    parser.add_argument("--variant", dest="variant", default=None, help="Variant id selector (csv).")
    parser.add_argument("--scorer", dest="scorer", default=None, help="Scorer id selector (csv).")
    _add_ui_flags(parser)
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint.")
    parser.add_argument(
        "--rerun-failed-only",
        action="store_true",
        help="Run only failed trials from the latest run.",
    )
    parser.add_argument("--checkpoint-key", default=None, help="Checkpoint key override.")
    parser.add_argument(
        "--keys",
        default=None,
        help="Simulated interactive key sequence (e.g. 'pfar') for automation/tests.",
    )
    _add_runtime_flags(parser)
    _add_web_monitor_flags(parser)
    return parser


def _add_ui_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cli-ui",
        action="store_true",
        help="Enable legacy live CLI renderer (default uses plain terminal logs + background Web monitor).",
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Disable terminal progress output (keeps Web monitor auto-start unless --no-web-monitor is set).",
    )
    parser.add_argument("--ui-refresh-ms", type=int, default=None, help="UI refresh interval in milliseconds.")
    parser.add_argument("--ui-max-events", type=int, default=None, help="UI event buffer max entries.")
    parser.add_argument("--ui-max-failures", type=int, default=None, help="UI failure buffer max entries.")
    parser.add_argument("--ui-max-active-trials", type=int, default=None, help="UI active trial buffer max entries.")
    parser.add_argument(
        "--ui-refresh-profile",
        choices=["smooth", "balanced", "low_cpu"],
        default=None,
        help="UI refresh profile.",
    )
    parser.add_argument(
        "--ui-theme",
        choices=["contrast", "quiet", "research", "research_redops"],
        default="research",
        help="UI theme mode.",
    )
    parser.add_argument(
        "--ui-mode",
        choices=["auto", "default", "qa_dense", "ops_dense", "compare_dense"],
        default=None,
        help="UI panel mode preset.",
    )
    parser.add_argument("--ui-no-banner", action="store_true", help="Start with banner collapsed.")


def _add_runtime_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-running-trials", type=int, default=None, help="Max concurrently executing trials.")
    parser.add_argument("--max-container-slots", type=int, default=None, help="Max concurrent container/sandbox slots.")
    parser.add_argument("--max-builds", type=int, default=None, help="Max concurrent container/image builds.")
    parser.add_argument("--max-scoring-tasks", type=int, default=None, help="Max concurrent scoring tasks.")
    parser.add_argument(
        "--keep-containers",
        action="store_true",
        help="Preserve runtime-owned containers after the run for debugging.",
    )
    parser.add_argument(
        "--keep-failed-containers",
        action="store_true",
        help="Preserve runtime-owned containers only for non-success trials.",
    )
    parser.add_argument(
        "--provider-budget",
        action="append",
        default=None,
        help="Provider concurrency budget in the form provider_id=n (repeatable).",
    )
    parser.add_argument(
        "--experiment-id",
        default=None,
        help="Optional experiment id for cross-run aggregation.",
    )


def _add_web_monitor_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-web-monitor",
        action="store_true",
        help="Disable auto-start of the web monitor during eval.",
    )
    parser.add_argument("--web-monitor-host", default="127.0.0.1", help="Web monitor host.")
    parser.add_argument("--web-monitor-port", type=int, default=8765, help="Web monitor port.")
    parser.add_argument(
        "--web-monitor-poll-interval-sec",
        type=float,
        default=0.5,
        help="Web monitor poll interval for run discovery.",
    )
