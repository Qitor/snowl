"""AgentBench OS benchmark adapter exports."""

import warnings

warnings.warn(
    "snowl.benchmarks.agent_bench_os is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.agent_bench_os in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.agent_bench_os.adapter import AgentBenchOSBenchmarkAdapter
from snowl.benchmarks.agent_bench_os.scorer import AgentBenchOSScorer

__all__ = ["AgentBenchOSBenchmarkAdapter", "AgentBenchOSScorer"]
