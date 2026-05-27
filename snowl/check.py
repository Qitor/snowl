"""Post-install health check: python -m snowl.check

Runs Snowl diagnostics and prints a summary of the installation health.
Exit code 0 if all checks pass, 1 otherwise.
"""

from snowl.cli_modules.check import _cmd_check

raise SystemExit(_cmd_check())
