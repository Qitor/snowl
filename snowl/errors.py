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


class PolicyViolationError(Exception):
    """Raised when a tool call violates runtime policy enforcement.

    Attributes:
        tool_name: The tool that triggered the violation.
        violation_type: Category of violation (e.g. 'forbidden_tool', 'max_calls_exceeded').
        detail: Human-readable description of the violation.
    """

    def __init__(self, tool_name: str, violation_type: str, detail: str = "") -> None:
        self.tool_name = tool_name
        self.violation_type = violation_type
        self.detail = detail
        super().__init__(f"Policy violation on '{tool_name}': {violation_type} — {detail}")
