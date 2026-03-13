"""Python module entrypoint for `python -m snowl`.

Framework role:
- Delegates process startup to `snowl.cli.main` so module invocation and installed CLI behavior stay identical.

Runtime/usage wiring:
- Thin bootstrap only; argument parsing, command routing, and run orchestration live in `snowl.cli`.

Change guardrails:
- Keep this file side-effect free besides invoking CLI main.
"""

from __future__ import annotations

import sys

from snowl.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
