"""QitOS framework adapter for Snowl evaluation.

Maps QitOS concepts to Snowl:
- AgentModule → Snowl Agent (via wrap())
- QitOS Task/Engine → Snowl AgentState (via unwrap_state/wrap_result)
- QitOS BaseTool → Snowl ToolSpec (via wrap_tools)
- QitOS Decision/Observation trace → Snowl Actions

The ``qitos`` package is a soft dependency — it is only imported at runtime
when the adapter is actually used, so Snowl can be installed without it.
"""

from __future__ import annotations

import importlib
from typing import Any

from snowl.adapters.base import BaseFrameworkAdapter
from snowl.core.agent import AgentState, StopReason


def _check_qitos_available() -> None:
    """Verify the ``qitos`` package is installed.

    Raises ImportError with a helpful message if not found.
    """
    try:
        importlib.import_module("qitos")
    except ImportError as exc:
        raise ImportError(
            "The 'qitos' package is required for the QitOS adapter. "
            "Install it with: pip install qitos"
        ) from exc


class QitOSAdapter(BaseFrameworkAdapter):
    """Adapter for QitOS AgentModule → Snowl Agent."""

    @property
    def framework_name(self) -> str:
        return "qitos"

    def wrap(self, agent_module: Any, **kwargs: Any) -> _QitOSAgent:
        """Wrap a QitOS AgentModule as a Snowl-compatible Agent.

        Args:
            agent_module: A QitOS AgentModule instance.
            **kwargs: Additional configuration (max_steps, workspace, etc.)

        Returns:
            A Snowl-compatible agent that delegates to the QitOS module.
        """
        _check_qitos_available()
        return _QitOSAgent(agent_module=agent_module, config=kwargs)

    def unwrap_state(self, snowl_state: AgentState) -> Any:
        """Convert Snowl AgentState to a QitOS-compatible task description."""
        if snowl_state.messages:
            last_msg = snowl_state.messages[-1]
            if isinstance(last_msg, dict):
                return last_msg.get("content", str(last_msg))
            return str(last_msg)
        return ""

    def wrap_result(self, framework_result: Any, snowl_state: AgentState) -> AgentState:
        """Convert QitOS EngineResult to updated Snowl AgentState."""
        output_text = ""

        if hasattr(framework_result, "task_result"):
            task_result = framework_result.task_result
            if hasattr(task_result, "final_answer") and task_result.final_answer:
                output_text = str(task_result.final_answer)
            elif hasattr(task_result, "output"):
                output_text = str(task_result.output)
        elif hasattr(framework_result, "step_summaries"):
            summaries = framework_result.step_summaries or []
            parts = []
            for s in summaries:
                if hasattr(s, "summary"):
                    parts.append(str(s.summary))
                else:
                    parts.append(str(s))
            output_text = "\n".join(parts)
        else:
            output_text = str(framework_result)

        stop = StopReason.COMPLETED
        if hasattr(framework_result, "cancel") and framework_result.cancel:
            stop = StopReason.CANCELLED

        return AgentState(
            messages=snowl_state.messages + [{"role": "assistant", "content": output_text}],
            output=output_text,
            stop_reason=stop,
        )

    def wrap_tools(self, snowl_tools: list[Any]) -> list[Any]:
        """Convert Snowl tool specs to QitOS BaseTool instances.

        This is a best-effort conversion. For full tool interop,
        provide QitOS-native tools directly to the AgentModule.
        """
        return snowl_tools


class _QitOSAgent:
    """Snowl Agent wrapper around a QitOS AgentModule."""

    def __init__(self, agent_module: Any, config: dict[str, Any] | None = None) -> None:
        self._module = agent_module
        self._config = config or {}
        self.agent_id = f"qitos:{getattr(agent_module, 'name', 'unknown')}"

    async def run(
        self,
        state: AgentState,
        context: Any,
        tools: Any = None,
    ) -> AgentState:
        """Execute the QitOS AgentModule and return updated state."""
        instruction = ""
        if state.messages:
            for msg in reversed(state.messages):
                content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                role = msg.get("role", "") if isinstance(msg, dict) else ""
                if role in ("user", "system") and content.strip():
                    instruction = content.strip()
                    break

        if not instruction:
            instruction = str(state.output or "")

        try:
            result = self._module.run(
                task=instruction,
                max_steps=self._config.get("max_steps"),
                workspace=self._config.get("workspace"),
            )
        except Exception as exc:
            return AgentState(
                messages=state.messages,
                output=f"QitOS execution error: {exc}",
                stop_reason=StopReason.ERROR,
            )

        adapter = QitOSAdapter()
        return adapter.wrap_result(result, state)
