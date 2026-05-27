"""Registry sub-command parser."""

from __future__ import annotations

import argparse


def add_registry_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("registry", help="Registry inspection and diagnostics.")
    registry_sub = parser.add_subparsers(dest="registry_command", required=True)
    registry_list = registry_sub.add_parser("list", help="List all registered components.")
    registry_list.add_argument("--kind", choices=["benchmark", "adapter", "environment_provider"], default=None, help="Filter by component kind.")
    registry_doctor = registry_sub.add_parser("doctor", help="Run registry health diagnostics.")
    registry_info = registry_sub.add_parser("info", help="Show details for a named component.")
    registry_info.add_argument("name", help="Component name to look up.")
    return parser
