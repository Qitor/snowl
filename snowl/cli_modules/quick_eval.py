"""Quick-eval command implementation."""

from __future__ import annotations

import importlib
import json


def _cmd_quick_eval(
    agent: str,
    benchmark: str | None,
    samples: str | None,
    scorer: str,
    limit: int | None,
    max_tokens: int,
) -> int:
    """Handle the ``quick-eval`` CLI subcommand."""
    from snowl.quick_eval import quick_eval_sync

    # Parse "module:function" agent spec
    if ":" not in agent:
        print(f"Error: --agent must be in module:function format (e.g. my_module:my_fn), got '{agent}'")
        return 1
    mod_path, fn_name = agent.rsplit(":", 1)
    try:
        mod = importlib.import_module(mod_path)
    except ImportError as exc:
        print(f"Error: could not import module '{mod_path}': {exc}")
        return 1
    agent_fn = getattr(mod, fn_name, None)
    if agent_fn is None:
        print(f"Error: module '{mod_path}' has no attribute '{fn_name}'")
        return 1

    # Load samples from JSON if provided
    sample_list = None
    if samples:
        try:
            with open(samples) as f:
                sample_list = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: could not load samples from '{samples}': {exc}")
            return 1

    if not benchmark and not sample_list:
        print("Error: provide either --benchmark or --samples")
        return 1

    try:
        result = quick_eval_sync(
            agent=agent_fn,
            benchmark=benchmark,
            samples=sample_list,
            scorer=scorer,
            limit=limit,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    print(result)
    return 0
