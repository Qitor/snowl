"""Aggregation package export surface for artifact schemas and summary builders.

Framework role:
- Centralizes public access to schema constants and `aggregate_outcomes` so callers avoid deep module imports.

Runtime/usage wiring:
- Used by eval/reporting layers when writing or validating aggregate result artifacts.

Change guardrails:
- Update exports alongside schema/version changes to avoid split-brain imports.
"""

from snowl.aggregator.schema import AGGREGATE_SCHEMA_URI, RESULT_SCHEMA_URI, RESULT_SCHEMA_VERSION
from snowl.aggregator.summary import AggregateResult, aggregate_outcomes

__all__ = [
    "AGGREGATE_SCHEMA_URI",
    "RESULT_SCHEMA_URI",
    "RESULT_SCHEMA_VERSION",
    "AggregateResult",
    "aggregate_outcomes",
]
