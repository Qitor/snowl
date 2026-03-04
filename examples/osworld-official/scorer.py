from __future__ import annotations

from snowl.benchmarks.osworld import OSWorldScorer
from snowl.core import scorer as declare_scorer


@declare_scorer()
def scorer() -> OSWorldScorer:
    return OSWorldScorer()
