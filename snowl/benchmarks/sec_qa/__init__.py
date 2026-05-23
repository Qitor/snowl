import warnings

warnings.warn(
    "snowl.benchmarks.sec_qa is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.sec_qa in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.sec_qa.adapter import SecQABenchmarkAdapter

__all__ = ["SecQABenchmarkAdapter"]
