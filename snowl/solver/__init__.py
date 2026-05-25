"""Built-in Solvers for composable evaluation pipelines.

Framework role:
- Provides ready-to-use Solvers that compose into chains via ``chain()``.
- ``generate()`` is the primary Solver that calls the model with a tool-use loop.
- ``system_message()``, ``use_tools()``, ``prompt_template()``, and ``submit_tool()``
  are setup/modification Solvers that transform state before generation.

Runtime/usage wiring:
- Users compose Solvers: ``chain(system_message("..."), use_tools(...), generate())``
- The ``generate`` function parameter injected by the framework is the entry
  point for model calls; ``generate()`` Solver invokes it with tool resolution.

Change guardrails:
- Built-in Solvers must not import from ``snowl.runtime`` or ``snowl.benchmarks``.
- They may import from ``snowl.core`` and ``snowl.model.base`` only.
"""

from snowl.solver._generate import generate
from snowl.solver._prompt import prompt_template, system_message, user_message
from snowl.solver._submit import submit_tool
from snowl.solver._use_tools import use_tools
from snowl.solver.resolve import resolve_solver_chain

__all__ = [
    "generate",
    "prompt_template",
    "resolve_solver_chain",
    "submit_tool",
    "system_message",
    "use_tools",
    "user_message",
]
