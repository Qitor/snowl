import warnings

warnings.warn(
    "snowl.benchmarks.xstest is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.xstest in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.xstest.adapter import XSTestBenchmarkAdapter
from snowl.benchmarks.xstest.scorer import XSTestScorer

__all__ = ["XSTestBenchmarkAdapter", "XSTestScorer"]
