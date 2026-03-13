"""AgentSafetyBench package exports for adapter/runtime/scorer integration.

Framework role:
- Exposes benchmark-specific adapter plus runtime helpers used to execute and score AgentSafetyBench cases.

Runtime/usage wiring:
- Consumed by registry wiring and benchmark workflows that need direct runtime helper access.

Change guardrails:
- Keep benchmark-specific logic scoped to this package; shared runtime contracts should remain generic.
"""

from snowl.benchmarks.agentsafetybench.adapter import AgentSafetyBenchBenchmarkAdapter
from snowl.benchmarks.agentsafetybench.runtime import (
    agentsafetybench_root,
    build_openai_agent_api,
    execute_agentsafetybench_case,
    persist_agentsafetybench_scores,
    persist_agentsafetybench_trajectory,
    resolve_agentsafetybench_output_dir,
    score_agentsafetybench_output,
)
from snowl.benchmarks.agentsafetybench.scorer import AgentSafetyBenchScorer

__all__ = [
    "AgentSafetyBenchBenchmarkAdapter",
    "AgentSafetyBenchScorer",
    "agentsafetybench_root",
    "build_openai_agent_api",
    "execute_agentsafetybench_case",
    "persist_agentsafetybench_scores",
    "persist_agentsafetybench_trajectory",
    "resolve_agentsafetybench_output_dir",
    "score_agentsafetybench_output",
]
