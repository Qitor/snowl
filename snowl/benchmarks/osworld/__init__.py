"""OSWorld benchmark package exports.

Framework role:
- Exposes OSWorld adapter and scorer entrypoints used by registry wiring and direct imports.

Runtime/usage wiring:
- Enables benchmark resolution without importing deeper OSWorld internals.

Change guardrails:
- Keep this file import-light; heavy OSWorld runtime setup belongs in provider/evaluator modules.
"""

from snowl.benchmarks.osworld.adapter import OSWorldBenchmarkAdapter
from snowl.benchmarks.osworld.scorer import OSWorldScorer, osworld

__all__ = ["OSWorldBenchmarkAdapter", "OSWorldScorer", "osworld"]

