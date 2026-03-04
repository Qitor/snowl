"""Aggregator APIs."""

from snowl.aggregator.schema import AGGREGATE_SCHEMA_URI, RESULT_SCHEMA_URI, RESULT_SCHEMA_VERSION
from snowl.aggregator.summary import AggregateResult, aggregate_outcomes

__all__ = [
    "AGGREGATE_SCHEMA_URI",
    "RESULT_SCHEMA_URI",
    "RESULT_SCHEMA_VERSION",
    "AggregateResult",
    "aggregate_outcomes",
]
