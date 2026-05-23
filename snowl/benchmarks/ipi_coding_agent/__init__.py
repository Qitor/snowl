"""Coding-agent prompt-injection benchmark exports."""

import warnings

warnings.warn(
    "snowl.benchmarks.ipi_coding_agent is deprecated and will move to snowl-evals. "
    "Install snowl-evals and import from snowl_evals.ipi_coding_agent in new code.",
    DeprecationWarning,
    stacklevel=2,
)

from snowl.benchmarks.ipi_coding_agent.adapter import IPICodingAgentBenchmarkAdapter
from snowl.benchmarks.ipi_coding_agent.scorer import IPICodingAgentScorer

__all__ = ["IPICodingAgentBenchmarkAdapter", "IPICodingAgentScorer"]
