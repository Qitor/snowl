"""Aggregation package export surface for artifact schemas and summary builders.

Framework role:
- Centralizes public access to schema constants and aggregation functions so callers avoid deep module imports.

Runtime/usage wiring:
- Used by eval/reporting layers when writing or validating aggregate result artifacts.

Change guardrails:
- Update exports alongside schema/version changes to avoid split-brain imports.
"""

from snowl.aggregator.schema import (
    AGGREGATE_SCHEMA_URI,
    AGGREGATE_SCHEMA_URI_V2,
    BENCHMARK_SUMMARY_SCHEMA_URI,
    DOMAIN_SUMMARY_SCHEMA_URI,
    LEADERBOARD_ROW_SCHEMA_URI,
    RESULT_SCHEMA_URI,
    RESULT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION_V2,
)
from snowl.aggregator.summary import (
    AggregateResult,
    BenchmarkRow,
    DomainRow,
    LeaderboardRow,
    RiskOverview,
    aggregate_benchmark_rows,
    aggregate_domain_rows,
    aggregate_leaderboard_rows,
    aggregate_outcomes,
    build_risk_overview,
    compute_risk_index,
)

__all__ = [
    # Schema constants
    "AGGREGATE_SCHEMA_URI",
    "AGGREGATE_SCHEMA_URI_V2",
    "BENCHMARK_SUMMARY_SCHEMA_URI",
    "DOMAIN_SUMMARY_SCHEMA_URI",
    "LEADERBOARD_ROW_SCHEMA_URI",
    "RESULT_SCHEMA_URI",
    "RESULT_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION_V2",
    # V1 aggregation
    "AggregateResult",
    "aggregate_outcomes",
    # V2 aggregation
    "BenchmarkRow",
    "DomainRow",
    "LeaderboardRow",
    "RiskOverview",
    "aggregate_benchmark_rows",
    "aggregate_domain_rows",
    "aggregate_leaderboard_rows",
    "build_risk_overview",
    "compute_risk_index",
]
