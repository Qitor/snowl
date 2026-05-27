"""Examples sub-command parser."""

from __future__ import annotations

import argparse


def add_examples_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("examples", help="Examples validation commands.")
    examples_sub = parser.add_subparsers(dest="examples_command", required=True)
    examples_check = examples_sub.add_parser("check", help="Validate examples folder layout.")
    examples_check.add_argument("path", nargs="?", default="examples", help="Examples root path.")
    return parser
