"""Quick-eval sub-command parser."""

from __future__ import annotations

import argparse


def add_quick_eval_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser("quick-eval", help="Evaluate an agent in one command — no project.yml required.")
    parser.add_argument("--agent", required=True, help="Agent as module:function (e.g. my_module:my_fn).")
    parser.add_argument("--benchmark", default=None, help="Built-in benchmark name (e.g. strongreject).")
    parser.add_argument("--samples", default=None, help="Path to JSON file with sample dicts.")
    parser.add_argument("--scorer", default="includes", help="Scorer name. Default: includes.")
    parser.add_argument("--limit", type=int, default=None, help="Max number of samples to evaluate.")
    parser.add_argument("--max-tokens", type=int, default=256, help="Token limit for agent responses.")
    return parser
