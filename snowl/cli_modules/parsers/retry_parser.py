"""Retry sub-command parser."""

from __future__ import annotations

import argparse

from snowl.cli_modules.parsers.eval_parser import _add_ui_flags, _add_runtime_flags, _add_web_monitor_flags


def add_retry_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("retry", help="Retry unfinished and non-success trials for an existing run.")
    parser.add_argument("run_id", help="Run id to recover in place.")
    parser.add_argument("--project", default=".", help="Project root or project.yml used to resolve the run source.")
    _add_ui_flags(parser)
    _add_runtime_flags(parser)
    _add_web_monitor_flags(parser)
    return parser
