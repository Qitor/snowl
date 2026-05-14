"""Trial data export utilities for snowl.

Framework role:
- Converts internal trial outcomes into portable formats for external consumption.
- Supports OpenAI-compatible conversation JSON as the primary export format.
"""

from snowl.export.openai_trace import outcome_to_openai_conversation

__all__ = ["outcome_to_openai_conversation"]
