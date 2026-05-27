"""Parser builders for the Snowl CLI."""

from __future__ import annotations

import argparse

from snowl.cli_modules.parsers.eval_parser import add_eval_parser
from snowl.cli_modules.parsers.retry_parser import add_retry_parser
from snowl.cli_modules.parsers.bench_parser import add_bench_parser
from snowl.cli_modules.parsers.web_parser import add_web_parser
from snowl.cli_modules.parsers.report_parsers import add_report_parser, add_compare_parser, add_rescore_parser, add_export_parser
from snowl.cli_modules.parsers.registry_parser import add_registry_parser
from snowl.cli_modules.parsers.leaderboard_parser import add_leaderboard_parser
from snowl.cli_modules.parsers.check_parser import add_check_parser
from snowl.cli_modules.parsers.quick_eval_parser import add_quick_eval_parser
from snowl.cli_modules.parsers.suite_parser import add_suite_parser
from snowl.cli_modules.parsers.examples_parser import add_examples_parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snowl")
    sub = parser.add_subparsers(dest="command", required=True)

    add_eval_parser(sub)
    add_retry_parser(sub)
    add_bench_parser(sub)
    add_suite_parser(sub)
    add_examples_parser(sub)
    add_web_parser(sub)
    add_report_parser(sub)
    add_compare_parser(sub)
    add_rescore_parser(sub)
    add_export_parser(sub)
    add_registry_parser(sub)
    add_leaderboard_parser(sub)
    add_check_parser(sub)
    add_quick_eval_parser(sub)

    return parser
