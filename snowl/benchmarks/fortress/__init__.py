import warnings

warnings.warn(
    "snowl.benchmarks.fortress is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.fortress in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.fortress.adapter import FortressBenchmarkAdapter
from snowl.benchmarks.fortress.scorer import FortressAdversarialScorer, FortressBenignScorer

__all__ = ["FortressBenchmarkAdapter", "FortressAdversarialScorer", "FortressBenignScorer"]
