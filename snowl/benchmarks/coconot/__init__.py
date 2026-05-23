import warnings

warnings.warn(
    "snowl.benchmarks.coconot is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.coconot in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.coconot.adapter import CoconotBenchmarkAdapter
from snowl.benchmarks.coconot.scorer import CoconotScorer

__all__ = ["CoconotBenchmarkAdapter", "CoconotScorer"]
