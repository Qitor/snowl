"""MASK benchmark package exports."""

import warnings

warnings.warn(
    "snowl.benchmarks.mask is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.mask in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.mask.adapter import MASKBenchmarkAdapter

__all__ = ["MASKBenchmarkAdapter"]
