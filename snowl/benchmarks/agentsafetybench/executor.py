"""AgentSafetyBench executor middleware: intercepts sentinel stub results and
delegates to dynamically-loaded environment tool implementations.

Framework role:
- ToolMiddleware that bridges Agent-SafetyBench's per-environment Python
  tool implementations into Snowl's ReActAgent middleware chain.

Runtime/usage wiring:
- Created per-sample by ``AgentSafetyBenchAgent`` and wired into ReActAgent's
  middleware list.

Change guardrails:
- Must stay compatible with the ToolMiddleware protocol.
- Must not import from the Agent-SafetyBench Python package.
"""

from __future__ import annotations

from typing import Any

from snowl.core import ToolSpec
from snowl.tools.middleware import ToolMiddleware

from snowl.benchmarks.agentsafetybench.env_loader import (
    AGENTSAFETYBENCH_ENV_DIR,
    SnowlBaseEnv,
    load_environment_class,
)


AGENTSAFETYBENCH_SENTINEL: dict[str, bool] = {"__agentsafetybench__": True}


def make_agentsafetybench_stub_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> ToolSpec:
    """Create a stub ToolSpec whose callable returns the AgentSafetyBench sentinel."""
    def _stub(**kwargs: Any) -> dict[str, bool]:
        return AGENTSAFETYBENCH_SENTINEL

    return ToolSpec(
        name=name,
        description=description,
        parameters=parameters,
        callable=_stub,
    )


class AgentSafetyBenchExecutor:
    """ToolMiddleware that delegates to dynamically-loaded environment instances.

    For each sample, one executor is created per environment. The executor:
    1. Loads the environment class via ``load_environment_class()``
    2. Instantiates it with the sample's parameters
    3. On ``intercept_result``, detects the sentinel and calls the real
       environment's ``call_tool()`` method
    """

    def __init__(
        self,
        *,
        env_name: str,
        env_params: dict[str, Any] | None = None,
        tool_names: list[str] | None = None,
        env_dir: str | None = None,
    ) -> None:
        self.env_name = env_name
        self.tool_names = tool_names or []
        env_dir_path = env_dir or str(AGENTSAFETYBENCH_ENV_DIR)

        env_cls = load_environment_class(env_name, env_dir_path)
        if env_params:
            self.env_instance: SnowlBaseEnv = env_cls(parameters=env_params)
        else:
            self.env_instance = env_cls()

    async def intercept_call(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        return args

    async def intercept_result(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
    ) -> Any:
        if isinstance(result, dict) and result.get("__agentsafetybench__"):
            try:
                return self.env_instance.call_tool(tool_name, dict(args))
            except Exception as exc:
                return {"success": False, "message": f"Error executing {tool_name}: {exc}"}
        return result
