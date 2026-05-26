"""Canary stripping for evaluation sample inputs.

Canary markers in evaluation data can leak into agent responses, inflating
scores on canary-detection metrics. This module provides utilities to strip
those markers from sample inputs before they reach the agent.

Framework role:
- Provides ``strip_canary()`` as a data-preparation utility.
- Used by ``quick_eval()`` and the trial execution pipeline.

Runtime/usage wiring:
- Imported via ``from snowl.canary import strip_canary``.
- Called automatically by ``quick_eval()`` when ``strip_canaries=True``.

Change guardrails:
- ``strip_canary()`` signature is a public utility. Changes must be backwards-compatible.
"""

from __future__ import annotations

import re
from typing import Any

# Common canary marker patterns
_CANARY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<!--\s*canary\s*=\s*[^>]*-->", re.IGNORECASE),
    re.compile(r"#\s*canary\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\[CANARY:\s*\S+\]", re.IGNORECASE),
    re.compile(r"<<CANARY:\s*\S+>>", re.IGNORECASE),
]


def strip_canary(
    text: str,
    *,
    extra_patterns: list[str] | None = None,
) -> str:
    """Remove canary markers from text.

    Strips common canary patterns used in evaluation benchmarks:
    - ``<!--canary=...-->``  (HTML comments)
    - ``# canary: ...``      (comment-style)
    - ``[CANARY: ...]``      (bracket notation)
    - ``<<CANARY: ...>>``    (angle bracket notation)

    Args:
        text: Input text that may contain canary markers.
        extra_patterns: Additional regex patterns to strip.

    Returns:
        Text with canary markers removed.

    Example::

        from snowl.canary import strip_canary

        clean = strip_canary("Solve this. <!--canary=abc123--> Step 1...")
        # "Solve this.  Step 1..."
    """
    result = text
    for pattern in _CANARY_PATTERNS:
        result = pattern.sub("", result)
    if extra_patterns:
        for pat_str in extra_patterns:
            result = re.sub(pat_str, "", result)
    # Clean up multiple spaces left by removals
    result = re.sub(r"  +", " ", result).strip()
    return result


def strip_canary_from_sample(
    sample: dict[str, Any],
    *,
    input_key: str = "input",
    extra_patterns: list[str] | None = None,
) -> dict[str, Any]:
    """Strip canary markers from a sample's input field.

    Returns a new dict with the input field cleaned. The original sample
    is not modified.

    Args:
        sample: Sample dict with an ``input`` key (or ``input_key``).
        input_key: The key containing the text to strip.
        extra_patterns: Additional regex patterns to strip.

    Returns:
        New sample dict with canary-stripped input.
    """
    sample = dict(sample)
    text = sample.get(input_key)
    if isinstance(text, str) and text:
        sample[input_key] = strip_canary(text, extra_patterns=extra_patterns)
    return sample
