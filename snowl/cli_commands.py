"""Backward-compat re-export of eval and retry commands from cli_modules.eval.

The canonical definitions now live in ``snowl.cli_modules.eval``.
This module re-exports them so that existing ``from snowl.cli_commands import _cmd_eval``
and test monkeypatching continue to work.
"""

from snowl.cli_modules.eval import _cmd_eval, _cmd_retry, _print_summary  # noqa: F401

# Re-export transitive dependencies that tests patch directly on this module
from snowl.eval import run_eval  # noqa: F401
from snowl.cli_modules.monitor import _ManagedWebMonitor  # noqa: F401
