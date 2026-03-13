"""Agent package export surface for built-in agent implementations.

Framework role:
- Exposes default chat/ReAct agents and model-variant builders used by examples and benchmark configs.

Runtime/usage wiring:
- Imported by user projects and eval bootstrap code that resolves built-in agent symbols.

Change guardrails:
- Keep exports stable; changing names here can break project declarations and tutorials.
"""

from snowl.agents.chat_agent import ChatAgent
from snowl.agents.model_variants import build_model_variants
from snowl.agents.react_agent import ReActAgent

__all__ = ["ChatAgent", "ReActAgent", "build_model_variants"]
