"""Resolve declarative solver chain configs into executable Solver chains.

Framework role:
- Converts ``project.yml`` solver_chain config dicts into ``Chain`` objects.
- Looks up solver factories by name from the discovered solvers list.
- Injects ``model_client`` from the project provider config at resolution time.

Runtime/usage wiring:
- Called by the engine when a ``solver_chain_config`` is present on the variant/request.
- Defers model_client construction to resolution time (not discovery time).

Change guardrails:
- Must only import from ``snowl.core`` and ``snowl.solver``.
- Config format is declarative; no arbitrary code execution.
"""

from __future__ import annotations

from typing import Any

from snowl.core.mcp import MCPServerSpec, mcp_server_spec_from_dict
from snowl.core.solver import Chain, Solver, _resolve_solver, chain


# Registry of named solver factories
_SOLVER_FACTORIES: dict[str, Any] = {}


def register_solver_factory(name: str, factory: Any) -> None:
    """Register a solver factory by name for config-based resolution.

    Args:
        name: Solver name (e.g., 'system_message', 'generate').
        factory: A callable that produces a Solver when invoked with config kwargs.
    """
    _SOLVER_FACTORIES[name] = factory


def _init_default_factories() -> None:
    """Populate default solver factories from built-in solvers."""
    if _SOLVER_FACTORIES:
        return  # Already initialized

    from snowl.solver._prompt import SystemMessageSolver, UserMessageSolver, PromptTemplateSolver
    from snowl.solver._use_tools import UseToolsSolver
    from snowl.solver._submit import SubmitToolSolver

    register_solver_factory("system_message", lambda **kw: SystemMessageSolver(kw.get("content", "")))
    register_solver_factory("user_message", lambda **kw: UserMessageSolver(kw.get("content", "")))
    register_solver_factory("prompt_template", lambda **kw: PromptTemplateSolver(kw.get("template", ""), **kw.get("variables", {})))
    register_solver_factory("use_tools", lambda **kw: _make_use_tools(**kw))
    register_solver_factory("submit_tool", lambda **kw: SubmitToolSolver())
    register_solver_factory("mcp_server", lambda **kw: mcp_server_spec_from_dict(kw))


def _make_use_tools(**kw: Any) -> Any:
    """Build a UseToolsSolver from config kwargs, including optional mcp_servers."""
    from snowl.solver._use_tools import UseToolsSolver

    tools = kw.get("tools", [])
    mcp_servers_raw = kw.get("mcp_servers", [])
    mcp_servers = tuple(
        mcp_server_spec_from_dict(s) if isinstance(s, dict) else s
        for s in mcp_servers_raw
    )
    return UseToolsSolver(*tools, mcp_servers=mcp_servers)


def resolve_solver_chain(
    config: dict[str, Any],
    *,
    model_client: Any | None = None,
    discovered_solvers: list[Any] | None = None,
) -> Chain | Solver | None:
    """Resolve a solver chain config dict into an executable Solver chain.

    Config format::

        solver_chain:
          steps:
            - system_message:
                content: "You are a helpful assistant."
            - use_tools:
                tools: [bash, file_read]
            - submit_tool: {}
            - generate:
                max_steps: 10
                temperature: 0.2

    Shorthand format (steps as list of strings)::

        solver_chain:
          steps: [system_message, use_tools, submit_tool, generate]
          system_message:
            content: "You are a helpful assistant."
          generate:
            max_steps: 10

    Args:
        config: The solver_chain config dict from project.yml.
        model_client: The ChatModelClient to inject into generate() solver.
        discovered_solvers: List of @solver-decorated solver instances for lookup.

    Returns:
        A Solver or Chain, or None if config is empty.
    """
    if not config:
        return None

    _init_default_factories()

    steps = config.get("steps", [])
    if not steps:
        return None

    # Build lookup for discovered solvers by solver_id
    discovered_map: dict[str, Any] = {}
    if discovered_solvers:
        for s in discovered_solvers:
            sid = getattr(s, "solver_id", None)
            if isinstance(sid, str):
                discovered_map[sid] = s

    solvers: list[Any] = []
    for step in steps:
        if isinstance(step, str):
            # Shorthand: step name, config from top-level config
            step_name = step
            step_config = config.get(step_name, {})
            if not isinstance(step_config, dict):
                step_config = {}
        elif isinstance(step, dict):
            # Full format: {name: config}
            items = list(step.items())
            if len(items) != 1:
                continue
            step_name, step_config = items[0]
            if not isinstance(step_config, dict):
                step_config = {}
        else:
            continue

        # Try discovered solvers first
        if step_name in discovered_map:
            solvers.append(discovered_map[step_name])
            continue

        # Try built-in factories
        if step_name in _SOLVER_FACTORIES:
            factory = _SOLVER_FACTORIES[step_name]
            try:
                solver_instance = factory(**step_config)
                solvers.append(solver_instance)
            except Exception:
                pass
            continue

        # Special handling for generate() which needs model_client
        if step_name == "generate":
            if model_client is not None:
                from snowl.solver._generate import GenerateSolver
                gen_config = dict(step_config)
                gen_config.setdefault("max_steps", 8)
                gen_config.setdefault("temperature", 0.2)
                gen_solver = GenerateSolver(model_client, **gen_config)
                solvers.append(gen_solver)
            continue

    if not solvers:
        return None
    if len(solvers) == 1:
        return _resolve_solver(solvers[0])
    return chain(*solvers)
