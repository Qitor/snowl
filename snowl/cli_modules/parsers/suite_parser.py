"""Suite sub-command parser."""

from __future__ import annotations

import argparse


def add_suite_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("suite", help="Multi-benchmark suite commands.")
    suite_sub = parser.add_subparsers(dest="suite_command", required=True)
    suite_check = suite_sub.add_parser("check", help="Validate a suite.yml file.")
    suite_check.add_argument("path", help="Path to suite.yml.")
    suite_run = suite_sub.add_parser("run", help="Run benchmarks listed in a suite.yml file.")
    suite_run.add_argument("path", help="Path to suite.yml.")
    return parser
