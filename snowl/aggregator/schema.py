"""Artifact schema/version constants for normalized results and aggregate outputs.

Framework role:
- Centralizes schema URIs and version tags used in run artifacts.

Runtime/usage wiring:
- Referenced by eval artifact writers and tests asserting schema stability.

Change guardrails:
- Version/URI changes are contract changes; coordinate with downstream consumers.
"""

from __future__ import annotations

RESULT_SCHEMA_VERSION = "v1"
RESULT_SCHEMA_URI = "snowl://schemas/results/v1"
AGGREGATE_SCHEMA_URI = "snowl://schemas/aggregate/v1"

RESULT_SCHEMA_VERSION_V2 = "v2"
BENCHMARK_SUMMARY_SCHEMA_URI = "snowl://schemas/benchmark_summary/v2"
DOMAIN_SUMMARY_SCHEMA_URI = "snowl://schemas/domain_summary/v2"
LEADERBOARD_ROW_SCHEMA_URI = "snowl://schemas/leaderboard_row/v2"
AGGREGATE_SCHEMA_URI_V2 = "snowl://schemas/aggregate/v2"
