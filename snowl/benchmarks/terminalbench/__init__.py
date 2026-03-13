"""TerminalBench benchmark package exports.

Framework role:
- Exposes TerminalBench adapter/scorer entrypoints used by registry and runtime integration code.

Runtime/usage wiring:
- Keeps benchmark wiring concise while container/provider internals stay encapsulated elsewhere.

Change guardrails:
- Avoid adding side effects here; startup/runtime operations belong in provider layers.
"""

from snowl.benchmarks.terminalbench.adapter import TerminalBenchBenchmarkAdapter
from snowl.benchmarks.terminalbench.scorer import TerminalBenchScorer, terminalbench

__all__ = ["TerminalBenchBenchmarkAdapter", "TerminalBenchScorer", "terminalbench"]

