"""Base framework adapter — abstract contract for bridging external agent frameworks.

Framework role:
- Defines the adapter contract that all framework-specific adapters must implement.
- Provides ``wrap()`` to convert a framework agent into a Snowl ``Agent``.
- Optional ``unwrap_state()`` / ``wrap_result()`` for state translation.

Runtime/usage wiring:
- Subclass this to create a new adapter (e.g., LangGraphAdapter, QitOSAdapter).
- The ``wrap()`` method is the primary entry point used by ``AdapterRegistry``.

Change guardrails:
- Must only import from ``snowl.core``; no runtime/engine/third-party dependencies.
- Keep the adapter contract minimal — adapters are thin translation layers.

Reference:
- ``references/harbor/src/harbor/agents/base.py`` (BaseAgent setup/run separation)
- ``references/inspect_ai/src/inspect_ai/agent/_as_solver.py`` (Agent → Solver bridge)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from snowl.core.agent import Agent, AgentContext, AgentState


class BaseFrameworkAdapter(ABC):
    """Abstract base class for framework-specific agent adapters.

    Subclass this to create an adapter that bridges an external agent
    framework into Snowl's ``Agent`` Protocol. The primary method is
    ``wrap()``, which returns a Snowl ``Agent`` implementation.
    """

    @property
    @abstractmethod
    def framework_name(self) -> str:
        """Name of the adapted framework (e.g., 'langgraph', 'qitos')."""
        ...

    @abstractmethod
    def wrap(self, agent: Any, **kwargs: Any) -> Agent:
        """Wrap a framework-specific agent as a Snowl ``Agent``.

        Args:
            agent: The framework-specific agent object to wrap.
            **kwargs: Additional framework-specific configuration.

        Returns:
            An object implementing the Snowl ``Agent`` Protocol.
        """
        ...

    def unwrap_state(self, snowl_state: AgentState) -> Any:
        """Convert Snowl AgentState to framework-native state.

        Override this if the wrapped agent expects a different state shape.
        Default: return the Snowl state unchanged.
        """
        return snowl_state

    def wrap_result(self, framework_result: Any, snowl_state: AgentState) -> AgentState:
        """Convert framework-native result back to Snowl AgentState.

        Override this if the wrapped agent produces a different result shape.
        Default: return the Snowl state (assumes ``run()`` updated it directly).
        """
        return snowl_state

    def wrap_tools(self, snowl_tools: list[Any] | None) -> Any:
        """Convert Snowl ToolSpec list to framework-native tools.

        Override this for frameworks with their own tool system.
        Default: return None (tools not translated).
        """
        return None
