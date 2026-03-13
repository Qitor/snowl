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
