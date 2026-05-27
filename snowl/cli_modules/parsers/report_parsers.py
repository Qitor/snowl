"""Report, compare, rescore, and export sub-command parsers."""

from __future__ import annotations

import argparse


def add_report_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("report", help="Regenerate report from a previous run.")
    parser.add_argument("run_id", nargs="?", default="latest", help="Run id or 'latest'.")
    parser.add_argument("--project", default=".", help="Project root path.")
    parser.add_argument("--format", choices=["html", "json", "markdown"], default="html", help="Output format.")
    parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout for json/markdown, overwrite report.html for html).")
    return parser


def add_compare_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("compare", help="Compare results from two runs.")
    parser.add_argument("run_id_a", help="First run id.")
    parser.add_argument("run_id_b", help="Second run id.")
    parser.add_argument("--project", default=".", help="Project root path.")
    parser.add_argument("--format", choices=["html", "markdown", "json"], default="markdown", help="Output format.")
    parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout).")
    return parser


def add_rescore_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("rescore", help="Re-score trials from a previous run.")
    parser.add_argument("run_id", nargs="?", default="latest", help="Run id or 'latest'.")
    parser.add_argument("--project", default=".", help="Project root path.")
    parser.add_argument("--scorer", default=None, help="Scorer id selector (csv). Only re-score with these scorers.")
    return parser


def add_export_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("export", help="Export trial trace data in portable formats.")
    parser.add_argument("run_id", nargs="?", default="latest", help="Run id or 'latest'.")
    parser.add_argument("--project", "-p", default=".", help="Project root path.")
    parser.add_argument("--format", choices=["openai", "json", "jsonl"], default="openai", help="Export format (default: openai).")
    parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout).")
    parser.add_argument("--trial-key", default=None, help="Export a specific trial only.")
    return parser
