from __future__ import annotations

from snowl.benchmarks.terminalbench import TerminalBenchScorer
from snowl.core import scorer as declare_scorer


@declare_scorer()
def scorer() -> TerminalBenchScorer:
    return TerminalBenchScorer()
