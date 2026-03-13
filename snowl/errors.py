"""Shared exception types for Snowl contract and validation failures.

Framework role:
- Provides a framework-level error class (`SnowlValidationError`) used when user/project/task schemas are invalid.

Runtime/usage wiring:
- Raised across config loading, task/agent/scorer validation, and model config parsing.

Change guardrails:
- Preserve semantic meaning: use this class for actionable user-contract errors, not internal runtime faults.
"""

class SnowlValidationError(ValueError):
    """Raised when user-provided contracts violate Snowl schemas."""
