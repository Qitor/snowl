"""WMDP benchmark package exports."""

import warnings

warnings.warn(
    "snowl.benchmarks.wmdp is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.wmdp in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.wmdp.adapter import WMDPBenchmarkAdapter

__all__ = ["WMDPBenchmarkAdapter"]
