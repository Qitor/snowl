"""StrongReject benchmark package exports.

Framework role:
- Exposes StrongReject adapter/scorer symbols for registry and user-level benchmark composition.

Runtime/usage wiring:
- Imported during benchmark registration and docs/example snippets.

Change guardrails:
- Preserve symbol names for compatibility with existing project configurations.
"""

from snowl.benchmarks.strongreject.adapter import StrongRejectBenchmarkAdapter
from snowl.benchmarks.strongreject.scorer import StrongRejectScorer, strongreject

__all__ = ["StrongRejectBenchmarkAdapter", "StrongRejectScorer", "strongreject"]
