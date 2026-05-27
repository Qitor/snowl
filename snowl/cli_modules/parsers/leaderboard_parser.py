"""Leaderboard sub-command parser."""

from __future__ import annotations

import argparse


def add_leaderboard_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("leaderboard", help="Leaderboard operations: publish, list, compare.")
    leaderboard_sub = parser.add_subparsers(dest="leaderboard_command", required=True)
    lb_publish = leaderboard_sub.add_parser("publish", help="Publish run results to leaderboard.")
    lb_publish.add_argument("run_dir", help="Path to the run artifacts directory.")
    lb_list = leaderboard_sub.add_parser("list", help="List leaderboard entries.")
    lb_list.add_argument("--domain", default=None, help="Filter by domain.")
    lb_list.add_argument("--top", type=int, default=20, help="Show top N entries.")
    lb_list.add_argument("--cost-aware", action="store_true", default=False, help="Show cost-efficiency column when available.")
    lb_compare = leaderboard_sub.add_parser("compare", help="Compare two runs on the leaderboard.")
    lb_compare.add_argument("run_dir_a", help="Path to first run artifacts directory.")
    lb_compare.add_argument("run_dir_b", help="Path to second run artifacts directory.")
    return parser
