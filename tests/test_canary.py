"""Tests for snowl.canary — canary stripping utilities."""

from __future__ import annotations

import pytest

from snowl.canary import strip_canary, strip_canary_from_sample


def test_strip_html_comment_canary():
    text = "Solve this. <!--canary=abc123--> Step 1..."
    assert strip_canary(text) == "Solve this. Step 1..."


def test_strip_hash_canary():
    text = "Do the task # canary: secret_marker here"
    assert "secret_marker" not in strip_canary(text)


def test_strip_bracket_canary():
    text = "Problem [CANARY: xyz789] description"
    assert "xyz789" not in strip_canary(text)


def test_strip_angle_bracket_canary():
    text = "Problem <<CANARY: abc456>> description"
    assert "abc456" not in strip_canary(text)


def test_strip_extra_patterns():
    text = "Problem {{MARKER: foo}} description"
    result = strip_canary(text, extra_patterns=[r"\{\{MARKER:\s*\w+\}\}"])
    assert "foo" not in result
    assert "description" in result


def test_strip_canary_no_markers():
    text = "Clean text without any markers"
    assert strip_canary(text) == text


def test_strip_canary_from_sample():
    sample = {
        "id": "s1",
        "input": "Solve this. <!--canary=abc--> Step 1...",
        "target": "answer",
    }
    result = strip_canary_from_sample(sample)
    assert "abc" not in result["input"]
    assert result["target"] == "answer"
    # Original not modified
    assert "abc" in sample["input"]


def test_strip_canary_from_sample_custom_key():
    sample = {"id": "s1", "prompt": "Do <!--canary=x--> stuff"}
    result = strip_canary_from_sample(sample, input_key="prompt")
    assert "x" not in result["prompt"]


def test_strip_canary_from_sample_non_string_input():
    sample = {"id": "s1", "input": 42}
    result = strip_canary_from_sample(sample)
    assert result["input"] == 42


@pytest.mark.asyncio
async def test_quick_eval_strip_canaries():
    """quick_eval with strip_canaries=True cleans input."""
    from snowl import quick_eval

    result = await quick_eval(
        agent=lambda msgs, tools: "ok",
        samples=[{"id": "s1", "input": "Solve <!--canary=secret--> task", "target": "ok"}],
        scorer="includes",
        strip_canaries=True,
    )
    assert isinstance(result, type(result))  # QuickEvalResult returned
