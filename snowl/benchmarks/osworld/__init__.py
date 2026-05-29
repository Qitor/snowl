"""OSWorld benchmark package — thin re-export shim.

The OSWorld benchmark has been migrated to snowl-evals. This module
provides backward-compatible re-exports so existing imports continue
to work. New code should import from snowl_evals.osworld directly.
"""

from snowl_evals.osworld.adapter import OSWorldBenchmarkAdapter  # noqa: F401
from snowl_evals.osworld.scorer import OSWorldScorer, osworld  # noqa: F401

__all__ = ["OSWorldBenchmarkAdapter", "OSWorldScorer", "osworld"]
