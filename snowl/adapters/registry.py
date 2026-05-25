"""Adapter registry — register and discover framework adapters.

Framework role:
- Provides ``AdapterRegistry`` for registering ``BaseFrameworkAdapter`` subclasses.
- Supports Python entry_points for auto-discovery of installed adapters.
- ``get_default_adapter_registry()`` returns the singleton registry with built-in adapters.

Runtime/usage wiring:
- Discovery layer calls ``get_default_adapter_registry().get(framework_name)`` to find adapters.
- Users can register custom adapters programmatically or via entry_points.

Change guardrails:
- Must only import from ``snowl.core`` and ``snowl.adapters.base``.
- Registry is global state; keep operations thread-safe and idempotent.

Reference:
- ``references/inspect_ai/src/inspect_ai/_util/registry.py`` (type:name indexing + entry_points)
- ``references/harbor/src/harbor/agents/factory.py`` (_AGENT_MAP + import_path pattern)
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

from snowl.adapters.base import BaseFrameworkAdapter
from snowl.errors import SnowlValidationError


class AdapterRegistry:
    """Registry of framework adapters, keyed by framework name."""

    def __init__(self) -> None:
        self._adapters: dict[str, type[BaseFrameworkAdapter]] = {}

    def register(self, name: str, adapter_cls: type[BaseFrameworkAdapter]) -> None:
        """Register an adapter class under a framework name.

        Args:
            name: Framework name (e.g., 'langgraph', 'custom').
            adapter_cls: A ``BaseFrameworkAdapter`` subclass.

        Raises:
            SnowlValidationError: If name is empty or adapter_cls is not a subclass.
        """
        if not isinstance(name, str) or not name.strip():
            raise SnowlValidationError("Adapter name must be a non-empty string.")
        if not (isinstance(adapter_cls, type) and issubclass(adapter_cls, BaseFrameworkAdapter)):
            raise SnowlValidationError(
                f"Adapter must be a BaseFrameworkAdapter subclass, got {adapter_cls!r}."
            )
        self._adapters[name.strip()] = adapter_cls

    def get(self, name: str) -> BaseFrameworkAdapter:
        """Get an adapter instance by framework name.

        Args:
            name: Framework name to look up.

        Returns:
            An instance of the registered adapter.

        Raises:
            SnowlValidationError: If no adapter is registered under this name.
        """
        if name not in self._adapters:
            available = ", ".join(sorted(self._adapters)) or "(none)"
            raise SnowlValidationError(
                f"No adapter registered for framework '{name}'. "
                f"Available: {available}"
            )
        return self._adapters[name]()

    def has(self, name: str) -> bool:
        """Check if an adapter is registered under this name."""
        return name in self._adapters

    def list_frameworks(self) -> list[str]:
        """List all registered framework names."""
        return sorted(self._adapters.keys())

    @classmethod
    def from_entry_points(cls, group: str = "snowl.adapters") -> "AdapterRegistry":
        """Create a registry populated from Python entry_points.

        Args:
            group: The entry_points group name (default: 'snowl.adapters').

        Returns:
            A new AdapterRegistry with discovered adapters.
        """
        registry = cls()
        if sys.version_info >= (3, 12):
            eps = importlib.metadata.entry_points(group=group)
        else:
            eps = importlib.metadata.entry_points().get(group, [])

        for ep in eps:
            try:
                adapter_cls = ep.load()
                if isinstance(adapter_cls, type) and issubclass(adapter_cls, BaseFrameworkAdapter):
                    registry.register(ep.name, adapter_cls)
            except Exception:
                pass  # Skip broken entry points silently
        return registry


# ---------------------------------------------------------------------------
# Default singleton registry
# ---------------------------------------------------------------------------

_default_registry: AdapterRegistry | None = None


def get_default_adapter_registry() -> AdapterRegistry:
    """Return the default adapter registry with built-in adapters registered."""
    global _default_registry
    if _default_registry is None:
        _default_registry = AdapterRegistry()
        # Register built-in adapters
        from snowl.adapters.custom import CustomAdapter
        from snowl.adapters.langgraph import LangGraphAdapter
        from snowl.adapters.openai_agents import OpenAIAgentsAdapter
        from snowl.adapters.qitos import QitOSAdapter

        _default_registry.register("custom", CustomAdapter)
        _default_registry.register("langgraph", LangGraphAdapter)
        _default_registry.register("openai_agents", OpenAIAgentsAdapter)
        _default_registry.register("qitos", QitOSAdapter)

        # Also discover from entry_points
        try:
            ep_registry = AdapterRegistry.from_entry_points()
            for name in ep_registry.list_frameworks():
                if not _default_registry.has(name):
                    _default_registry._adapters[name] = ep_registry._adapters[name]
        except Exception:
            pass

    return _default_registry
