from __future__ import annotations

import json

import httpx

from snowl.core import ScoreContext, TaskResult, TaskStatus
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig
from snowl.scorer import chain, includes, match, model_as_judge_json, pattern, unit_test_results, weighted


def _result(content: str) -> TaskResult:
    return TaskResult(
        task_id="t1",
        agent_id="a1",
        sample_id="s1",
        seed=1,
        status=TaskStatus.SUCCESS,
        final_output={"content": content},
    )


def test_includes_case_insensitive() -> None:
    scorer = includes()
    out = scorer.score(
        _result("The final answer is Paris."),
        {},
        ScoreContext(task_id="t1", agent_id="a1", sample_metadata={"target": "paris"}),
    )
    assert out["includes"].value == 1.0


def test_match_end_ignoring_whitespace_and_punctuation() -> None:
    scorer = match(position="end")
    out = scorer.score(
        _result("Result =>  42!!! "),
        {},
        ScoreContext(task_id="t1", agent_id="a1", sample_metadata={"target": "42"}),
    )
    assert out["match"].value == 1.0


def test_pattern_extract_and_compare_target() -> None:
    scorer = pattern(r"answer\s*:\s*([A-Z]+)", group=1)
    out = scorer.score(
        _result("foo answer: BLUE bar"),
        {},
        ScoreContext(task_id="t1", agent_id="a1", sample_metadata={"target": "blue"}),
    )
    assert out["pattern"].value == 1.0
    assert out["pattern"].metadata["extracted"] == "BLUE"


def test_string_scorers_support_simple_lambda_extractors() -> None:
    scorer = includes(
        extract=lambda tr: tr.final_output["content"],
        target=lambda tr: tr.payload["expected_answer"],
    )
    out = scorer.score(
        TaskResult(
            task_id="t1",
            agent_id="a1",
            sample_id="s1",
            seed=1,
            status=TaskStatus.SUCCESS,
            final_output={"content": "hello WORLD"},
            payload={"expected_answer": "world"},
        ),
        {},
        ScoreContext(task_id="t1", agent_id="a1"),
    )
    assert out["includes"].value == 1.0


def test_model_as_judge_json_success_and_schema_validation() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": '{"score": 0.8, "reasoning": "good"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            },
        )

    client = OpenAICompatibleChatClient(
        OpenAICompatibleConfig(
            base_url="https://example.com/v1",
            api_key="k",
            model="judge-model",
            timeout=5,
            max_retries=0,
        ),
        transport=httpx.MockTransport(handler),
    )
    scorer = model_as_judge_json(
        model_name="judge-model",
        system_prompt="You are a judge for task {task_result.task_id}.",
        user_prompt=(
            "Evaluate output.\n"
            "task={task_id}\n"
            "sample={sample_id}\n"
            "target={target}\n"
            "output={output}\n"
            "extra={payload.extra_note}"
        ),
        schema={
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["score", "reasoning"],
            "additionalProperties": False,
        },
        client=client,
    )
    out = scorer.score(
        TaskResult(
            task_id="t1",
            agent_id="a1",
            sample_id="s1",
            seed=1,
            status=TaskStatus.SUCCESS,
            final_output={"content": "answer"},
            payload={"extra_note": "note-from-payload"},
        ),
        {},
        ScoreContext(task_id="t1", agent_id="a1", sample_metadata={"target": "target"}),
    )
    assert out["judge"].value == 0.8
    assert out["judge"].metadata["judge_parsed"]["reasoning"] == "good"
    assert "task=t1" in out["judge"].metadata["judge_prompt"]
    assert "extra=note-from-payload" in out["judge"].metadata["judge_prompt"]
    assert "task t1" in out["judge"].metadata["judge_system_prompt"]


def test_model_as_judge_json_returns_zero_on_invalid_schema_payload() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        bad_payload = json.dumps({"reasoning": "missing score"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": bad_payload}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            },
        )

    client = OpenAICompatibleChatClient(
        OpenAICompatibleConfig(
            base_url="https://example.com/v1",
            api_key="k",
            model="judge-model",
            timeout=5,
            max_retries=0,
        ),
        transport=httpx.MockTransport(handler),
    )
    scorer = model_as_judge_json(
        model_name="judge-model",
        system_prompt="Judge task {task_id}",
        user_prompt="Output is {output}. Target is {target}.",
        schema={
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["score", "reasoning"],
            "additionalProperties": False,
        },
        client=client,
    )
    out = scorer.score(
        _result("answer"),
        {},
        ScoreContext(task_id="t1", agent_id="a1", sample_metadata={"target": "target"}),
    )
    assert out["judge"].value == 0.0
    assert "judge_error" in out["judge"].metadata


def test_model_as_judge_json_template_missing_key_returns_zero_when_not_strict() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": '{"score": 1.0, "reasoning": "ok"}'}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
            },
        )

    client = OpenAICompatibleChatClient(
        OpenAICompatibleConfig(
            base_url="https://example.com/v1",
            api_key="k",
            model="judge-model",
            timeout=5,
            max_retries=0,
        ),
        transport=httpx.MockTransport(handler),
    )
    scorer = model_as_judge_json(
        model_name="judge-model",
        system_prompt="Judge {unknown_key}",
        user_prompt="Output {output}",
        strict_templates=False,
        client=client,
    )
    out = scorer.score(
        _result("answer"),
        {},
        ScoreContext(task_id="t1", agent_id="a1"),
    )
    assert out["judge"].value == 1.0


def test_unit_test_results_scorer_from_payload_and_trace() -> None:
    scorer = unit_test_results(parser_results_trace_event="terminalbench.parser_results")
    result_payload = TaskResult(
        task_id="t1",
        agent_id="a1",
        sample_id="s1",
        seed=1,
        status=TaskStatus.SUCCESS,
        final_output={"content": ""},
        payload={"parser_results": {"test_a": "passed", "test_b": "failed"}},
    )
    out_payload = scorer.score(
        result_payload,
        {},
        ScoreContext(task_id="t1", agent_id="a1", sample_metadata={"parser_name": "pytest"}),
    )
    assert out_payload["accuracy"].value == 0.0
    assert out_payload["pass_rate"].value == 0.5

    result_trace = _result("")
    out_trace = scorer.score(
        result_trace,
        {"trace_events": [{"event": "terminalbench.parser_results", "parser_results": {"test_only": "passed"}}]},
        ScoreContext(task_id="t1", agent_id="a1", sample_metadata={"parser_name": "pytest"}),
    )
    assert out_trace["accuracy"].value == 1.0


def test_unit_test_results_scorer_parses_pytest_output() -> None:
    scorer = unit_test_results()
    content = (
        "...\n"
        "================ short test summary info ================\n"
        "PASSED tests/test_outputs.py::test_ok\n"
        "FAILED tests/test_outputs.py::test_bad - AssertionError\n"
    )
    out = scorer.score(
        _result(content),
        {},
        ScoreContext(task_id="t1", agent_id="a1", sample_metadata={"parser_name": "pytest"}),
    )
    assert out["accuracy"].value == 0.0
    assert out["pass_rate"].value == 0.5


def test_weighted_composite_and_chain_support_partial_failures() -> None:
    class GoodA:
        scorer_id = "a"

        def score(self, task_result, trace, context):
            _ = (task_result, trace, context)
            from snowl.core import Score

            return {"accuracy": Score(value=0.8)}

    class GoodB:
        scorer_id = "b"

        def score(self, task_result, trace, context):
            _ = (task_result, trace, context)
            from snowl.core import Score

            return {"robustness": Score(value=0.4)}

    class Bad:
        scorer_id = "bad"

        def score(self, task_result, trace, context):
            _ = (task_result, trace, context)
            raise RuntimeError("boom")

    tr = _result("x")
    ctx = ScoreContext(task_id="t1", agent_id="a1")

    composite = weighted(
        [GoodA(), Bad(), GoodB()],
        weights={"a.accuracy": 0.75, "b.robustness": 0.25},
    )
    out = composite.score(tr, {}, ctx)
    assert round(out["weighted_score"].value, 6) == round(0.8 * 0.75 + 0.4 * 0.25, 6)
    assert out["weighted_score"].metadata["errors"]

    chained = chain([GoodA(), Bad(), GoodB()], namespace_metrics=True)
    out2 = chained.score(tr, {}, ctx)
    assert "a.accuracy" in out2
    assert "b.robustness" in out2
    assert out2["chain_error_count"].value == 1.0
