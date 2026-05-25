"""Framework adapter SDK — bridge any agent framework into Snowl evaluation.

Framework role:
- Provides ``BaseFrameworkAdapter`` as the abstract contract for all framework adapters.
- Ships built-in adapters for common frameworks (Custom, LangGraph, OpenAI Agents SDK, QitOS).
- ``AdapterRegistry`` manages adapter registration and discovery.

Runtime/usage wiring:
- Discovery layer uses ``AdapterRegistry`` to auto-wrap framework agents when
  ``project.yml`` declares a ``framework`` field.
- Adapters convert framework-specific agents into Snowl ``Agent`` Protocol implementations.

Change guardrails:
- Adapters must depend on ``snowl.core`` only; no runtime/engine imports.
- Each adapter is a thin translation layer, not a full framework integration.
"""

from snowl.adapters.base import BaseFrameworkAdapter
from snowl.adapters.registry import AdapterRegistry, get_default_adapter_registry

__all__ = [
    "BaseFrameworkAdapter",
    "AdapterRegistry",
    "get_default_adapter_registry",
]
