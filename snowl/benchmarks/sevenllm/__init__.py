import warnings

warnings.warn(
    "snowl.benchmarks.sevenllm is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.sevenllm in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.sevenllm.adapter import SevenLLMMCQBenchmarkAdapter

__all__ = ["SevenLLMMCQBenchmarkAdapter"]
