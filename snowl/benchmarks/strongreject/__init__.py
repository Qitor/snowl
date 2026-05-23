"""StrongReject benchmark package exports.

Framework role:
- Exposes StrongReject adapter/scorer symbols for registry and user-level benchmark composition.

Runtime/usage wiring:
- Imported during benchmark registration and docs/example snippets.

Change guardrails:
- Preserve symbol names for compatibility with existing project configurations.
- A deprecation warning is emitted when importing from this location;
  the canonical import path is now ``snowl_evals.strongreject``.
"""

import warnings

warnings.warn(
    "Importing from snowl.benchmarks.strongreject is deprecated. "
    "Install snowl-evals and use snowl_evals.strongreject instead.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.strongreject.adapter import StrongRejectBenchmarkAdapter
from snowl.benchmarks.strongreject.scorer import StrongRejectScorer, strongreject

__all__ = ["StrongRejectBenchmarkAdapter", "StrongRejectScorer", "strongreject"]
