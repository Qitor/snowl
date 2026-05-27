"""Check sub-command parser."""

from __future__ import annotations

import argparse


def add_check_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    sub.add_parser("check", help="Run installation health checks.")
    # check has no arguments
    return sub.choices["check"]
