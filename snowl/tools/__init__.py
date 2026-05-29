"""Tool package exports for terminal/gui ToolSpec builders.

Framework role:
- Exposes default toolset factories used when wiring agent execution contexts.

Runtime/usage wiring:
- Imported by eval/runtime paths that resolve tool specs for agents.

Change guardrails:
- Keep this module declarative; environment-side behavior belongs in concrete tool modules.
"""

from snowl.tools.gui import GuiToolset, build_gui_tools
from snowl.tools.terminal import TerminalToolset, build_terminal_tools
from snowl.tools.policy_approval import PolicyApprovalAdapter

__all__ = [
    "GuiToolset",
    "PolicyApprovalAdapter",
    "TerminalToolset",
    "build_gui_tools",
    "build_terminal_tools",
]
