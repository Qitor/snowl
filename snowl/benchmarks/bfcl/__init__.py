"""BFCL benchmark adapter exports."""

import warnings

warnings.warn(
    "snowl.benchmarks.bfcl is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.bfcl in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.bfcl.adapter import BFCLBenchmarkAdapter
from snowl.benchmarks.bfcl.scorer import BFCLScorer

__all__ = ["BFCLBenchmarkAdapter", "BFCLScorer"]
