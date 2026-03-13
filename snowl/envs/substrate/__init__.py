"""Low-level substrate exports used by higher-level environment adapters.

Framework role:
- Re-exports command/container/http primitives so env implementations share a consistent backend interface.

Runtime/usage wiring:
- Consumed by `terminal_env`, `gui_env`, and sandbox runtime internals.

Change guardrails:
- Keep this layer backend-focused; do not leak task/agent semantics into substrate utilities.
"""

from snowl.envs.substrate.command_runner import CommandRunner, CommandRunnerResult
from snowl.envs.substrate.container_backend import ContainerBackend
from snowl.envs.substrate.gui_action_translator import GuiActionTranslator
from snowl.envs.substrate.http_runner import HttpRunner, HttpRunnerError

__all__ = [
    "CommandRunner",
    "CommandRunnerResult",
    "ContainerBackend",
    "GuiActionTranslator",
    "HttpRunner",
    "HttpRunnerError",
]
