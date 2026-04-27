from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from snowl.benchmarks.agentharm import AgentHarmBenchmarkAdapter
from snowl.benchmarks.assets import DirectURLAsset, HFDatasetAsset, HFSnapshotFileAsset, stable_benchmark_id
from snowl.benchmarks.coconot import CoconotBenchmarkAdapter, CoconotScorer
from snowl.benchmarks.fortress import FortressAdversarialScorer, FortressBenchmarkAdapter
from snowl.benchmarks.registry import get_default_benchmark_registry
from snowl.benchmarks.xstest import XSTestBenchmarkAdapter, XSTestScorer
from snowl.core import AgentState, EnvSpec, Score, ScoreContext, StopReason, Task, TaskResult, TaskStatus, build_tool_spec
from snowl.runtime import TrialRequest, execute_trial
from snowl.scorer.choice import ChoiceAnswerScorer


class FakeJudgeClient:
    def __init__(self, content: str):
        self.content = content

    async def generate(self, messages, **kwargs):
        _ = (messages, kwargs)
        return {"message": {"role": "assistant", "content": self.content}}


def _result(content: str, *, sample_input: str = "prompt") -> TaskResult:
    return TaskResult(
        task_id="t",
        agent_id="a",
        sample_id="s",
        seed=1,
        status=TaskStatus.SUCCESS,
        final_output={"content": content, "message": {"content": content}},
        payload={"sample_input": {"input": sample_input}},
    )


def test_asset_resolver_hf_dataset_and_snapshot_and_direct_url(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SNOWL_BENCHMARK_CACHE", str(tmp_path))

    def fake_load_dataset(**kwargs):
        assert kwargs["revision"] == "rev"
        assert kwargs["cache_dir"].startswith(str(tmp_path))
        return [{"prompt": "hello"}]

    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()
    (snapshot_root / "data.json").write_text("{}", encoding="utf-8")

    def fake_snapshot_download(**kwargs):
        assert kwargs["revision"] == "rev"
        assert kwargs["allow_patterns"] == ["*.json"]
        return str(snapshot_root)

    monkeypatch.setitem(sys.modules, "datasets", SimpleNamespace(load_dataset=fake_load_dataset))
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=fake_snapshot_download))

    rows = HFDatasetAsset(source="org/ds", revision="rev", split="test").load_rows()
    assert rows == [{"prompt": "hello"}]
    assert HFSnapshotFileAsset(source="org/ds", revision="rev", relative_path="data.json", allow_patterns=("*.json",)).resolve_path().exists()

    class FakeResponse:
        content = b"abc"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("requests.get", lambda url, timeout: FakeResponse())
    path = DirectURLAsset(
        url="https://example.com/data.txt",
        sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        cache_name="data.txt",
    ).resolve_path()
    assert path.read_bytes() == b"abc"


def test_adapters_map_rows_to_snowl_samples() -> None:
    xstest = XSTestBenchmarkAdapter(rows=[{"prompt": "safe q", "label": "safe", "type": "t", "note": "n", "focus": "f"}])
    x_sample = list(xstest.load_tasks(split="test", limit=1)[0].iter_samples())[0]
    assert x_sample["id"].startswith("xstest-")
    assert x_sample["metadata"]["label"] == "safe"

    coconot = CoconotBenchmarkAdapter(rows=[{"id": "c1", "prompt": "q", "category": "cat", "subcategory": "sub"}])
    c_sample = list(coconot.load_tasks(split="test", limit=1)[0].iter_samples())[0]
    assert c_sample["metadata"]["refusal"]
    assert c_sample["metadata"]["category"] == "cat"

    fortress = FortressBenchmarkAdapter(
        rows=[{"ID": "f1", "adversarial_prompt": "bad", "benign_prompt": "benign", "rubric": ["r1", "r2"], "risk_domain": "D", "risk_subdomain": "S: long"}]
    )
    f_sample = list(fortress.load_tasks(split="train", limit=1)[0].iter_samples())[0]
    assert f_sample["metadata"]["num_dim"] == 2
    assert f_sample["metadata"]["risk_subdomain"] == "S"

    agentharm = AgentHarmBenchmarkAdapter(
        rows=[{"id": "a1", "split": "test_public", "prompt": "do thing", "category": "cyber", "target_functions": ["tool_a"], "grading_function": "grade_a"}]
    )
    a_sample = list(agentharm.load_tasks(split="test_public", limit=1)[0].iter_samples())[0]
    assert a_sample["metadata"]["tool_names"] == ["tool_a"]
    assert a_sample["metadata"]["grading_function"] == "grade_a"


def test_registry_includes_first_wave_benchmarks() -> None:
    names = {entry.info.name for entry in get_default_benchmark_registry().list()}
    assert {"xstest", "coconot", "fortress_adversarial", "fortress_benign", "agentharm", "agentharm_benign"} <= names


def test_choice_and_judge_scorers() -> None:
    choice = ChoiceAnswerScorer()
    out = choice.score(
        _result("Final answer: B"),
        {},
        ScoreContext(task_id="t", agent_id="a", sample_metadata={"choices": ["a", "b"], "target": "B"}),
    )
    assert out["accuracy"].value == 1.0

    xstest = XSTestScorer(model_name="judge", client=FakeJudgeClient("Reason\nGRADE: I"))
    x_scores = xstest.score(
        _result("I can't help.", sample_input="unsafe"),
        {},
        ScoreContext(task_id="t", agent_id="a", sample_metadata={"label": "unsafe"}),
    )
    assert x_scores["xstest_safety"].value == 1.0
    assert x_scores["refusal_rate"].value == 1.0

    coconot = CoconotScorer(model_name="judge", client=FakeJudgeClient("Reason\nUNACCEPTABLE"))
    c_scores = coconot.score(
        _result("Here you go"),
        {},
        ScoreContext(task_id="t", agent_id="a", sample_metadata={"subset": "original", "category": "cat"}),
    )
    assert c_scores["compliance_rate"].value == 1.0
    assert c_scores["noncompliance_score"].value == 0.0


def test_fortress_adversarial_majority_vote() -> None:
    scorer = FortressAdversarialScorer(
        model_names=["j1", "j2", "j3"],
        clients={
            "j1": FakeJudgeClient("GRADE: YY"),
            "j2": FakeJudgeClient("GRADE: YN"),
            "j3": FakeJudgeClient("GRADE: NN"),
        },
    )
    scores = scorer.score(
        _result("response", sample_input="prompt"),
        {},
        ScoreContext(task_id="t", agent_id="a", sample_metadata={"rubric": ["r1", "r2"], "num_dim": 2, "risk_domain": "D", "risk_subdomain": "S"}),
    )
    assert scores["ARS"].value == 0.5
    assert scores["ARS__risk_domain__D"].value == 0.5


def test_runtime_selects_per_sample_tools_and_errors_on_missing() -> None:
    calls: list[list[str]] = []

    def tool_a() -> str:
        return "a"

    def tool_b() -> str:
        return "b"

    class RecordingAgent:
        agent_id = "rec"

        async def run(self, state: AgentState, context, tools=None):
            _ = context
            calls.append([tool.name for tool in (tools or [])])
            state.output = {"message": {"role": "assistant", "content": "ok"}, "usage": {}}
            state.stop_reason = StopReason.COMPLETED
            return state

    class PassScorer:
        scorer_id = "pass"

        def score(self, task_result, trace, context):
            _ = (task_result, trace, context)
            return {"ok": Score(value=1.0)}

    task = Task(task_id="t", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([]))
    req = TrialRequest(
        task=task,
        agent=RecordingAgent(),
        scorer=PassScorer(),
        sample={"id": "s", "input": "hi", "metadata": {"tool_names": ["tool_a"]}},
        tools=[
            build_tool_spec(tool_a, name="tool_a"),
            build_tool_spec(tool_b, name="tool_b"),
        ],
    )
    out = asyncio.run(execute_trial(req))
    assert out.task_result.status.value == "success"
    assert calls == [["tool_a"]]

    missing = TrialRequest(
        task=task,
        agent=RecordingAgent(),
        scorer=PassScorer(),
        sample={"id": "s", "input": "hi", "metadata": {"tool_names": ["missing"]}},
        tools=[build_tool_spec(tool_a, name="tool_a")],
    )
    bad = asyncio.run(execute_trial(missing))
    assert bad.task_result.status.value == "error"
    assert bad.task_result.error is not None
    assert bad.task_result.error.code == "sample_tool_missing"


def test_stable_benchmark_id_is_deterministic() -> None:
    assert stable_benchmark_id("x", "a", "b") == stable_benchmark_id("x", "a", "b")
