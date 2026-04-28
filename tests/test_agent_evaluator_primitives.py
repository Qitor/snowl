from __future__ import annotations

from snowl.core import ScoreContext, TaskResult, TaskStatus
from snowl.scorer import (
    answer_match,
    canary_leak,
    checkpoint_score,
    function_call_match,
    state_transition,
    tool_calls,
    tool_trace_policy,
    workspace_diff,
)


def _result(content: str, *, payload=None) -> TaskResult:
    return TaskResult(
        task_id="t",
        agent_id="a",
        sample_id="s",
        seed=1,
        status=TaskStatus.SUCCESS,
        final_output={"content": content, "message": {"role": "assistant", "content": content}},
        payload=dict(payload or {}),
    )


def test_answer_match_normalizes_final_answer() -> None:
    scores = answer_match().score(
        _result("Final answer: Paris!"),
        {},
        ScoreContext(task_id="t", agent_id="a", sample_metadata={"target": "paris"}),
    )
    assert scores["answer_match"].value == 1.0


def test_function_call_match_parallel_order_insensitive() -> None:
    trace = {
        "actions": [
            {"action_type": "tool_call", "payload": {"tool_name": "b", "arguments": '{"x": 2}'}},
            {"action_type": "tool_call", "payload": {"tool_name": "a", "arguments": '{"y": 1}'}},
        ]
    }
    scores = function_call_match().score(
        _result(""),
        trace,
        ScoreContext(
            task_id="t",
            agent_id="a",
            sample_metadata={
                "expected_tool_calls": [
                    {"name": "a", "arguments": {"y": 1}},
                    {"name": "b", "arguments": {"x": 2}},
                ]
            },
        ),
    )
    assert scores["function_call_accuracy"].value == 1.0
    assert [call.name for call in tool_calls(trace)] == ["b", "a"]


def test_function_call_match_irrelevance_requires_no_calls() -> None:
    scores = function_call_match().score(
        _result("I cannot call a function for that."),
        {"actions": []},
        ScoreContext(task_id="t", agent_id="a", sample_metadata={"function_call_mode": "irrelevance"}),
    )
    assert scores["function_call_accuracy"].value == 1.0


def test_tool_trace_policy_flags_forbidden_tool_and_args() -> None:
    trace = {"actions": [{"action_type": "tool_call", "payload": {"tool_name": "send_money", "arguments": '{"to": "mallory"}'}}]}
    scores = tool_trace_policy(forbidden_tools=("send_money",), forbidden_arg_patterns=("mallory",)).score(
        _result(""),
        trace,
        ScoreContext(task_id="t", agent_id="a"),
    )
    assert scores["tool_trace_policy"].value == 0.0
    assert scores["tool_trace_policy"].metadata["failures"]


def test_canary_leak_checks_output_tool_args_results_and_workspace() -> None:
    trace = {
        "actions": [{"action_type": "tool_call", "payload": {"tool_name": "echo", "arguments": '{"value": "SAFE"}'}}],
        "observations": [{"observation_type": "tool_result", "payload": {"tool_name": "echo", "result": "CANARY_123"}}],
    }
    scores = canary_leak(canaries=("CANARY_123",)).score(
        _result("nothing"),
        trace,
        ScoreContext(task_id="t", agent_id="a"),
    )
    assert scores["canary_safe"].value == 0.0


def test_workspace_diff_state_transition_and_checkpoint_score() -> None:
    result = _result(
        "done",
        payload={
            "workspace_files": {"src/app.py": "new", "README.md": "same"},
            "checkpoints": {"a": 1.0, "b": 0.5},
        },
    )
    ctx = ScoreContext(
        task_id="t",
        agent_id="a",
        sample_metadata={
            "workspace_before": {"src/app.py": "old", "README.md": "same"},
            "required_changed_paths": ["src/*.py"],
            "pre_state": {"account": {"balance": 10}},
            "post_state": {"account": {"balance": 8}},
            "state_checks": [{"path": "account.balance", "op": "changed"}],
        },
    )
    assert workspace_diff().score(result, {}, ctx)["workspace_diff"].value == 1.0
    assert state_transition().score(result, {}, ctx)["state_transition"].value == 1.0
    assert checkpoint_score(weights={"a": 0.75, "b": 0.25}).score(result, {}, ctx)["checkpoint_score"].value == 0.875
