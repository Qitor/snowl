import warnings

warnings.warn(
    "snowl.benchmarks.cybermetric is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.cybermetric in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.cybermetric.adapter import CyberMetricBenchmarkAdapter

__all__ = ["CyberMetricBenchmarkAdapter"]
