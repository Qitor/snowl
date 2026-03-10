from __future__ import annotations

import asyncio
import json
from pathlib import Path

from snowl.core import AgentVariant, make_agent_variant
from snowl.errors import SnowlValidationError
from snowl.cli import main
from snowl.eval import run_eval


def _write_task_and_scorer(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task
task = Task(
    task_id="t1",
    env_spec=EnvSpec(env_type="local"),
    sample_iter_factory=lambda: iter([{"id":"s1", "input":"x"}]),
)
""",
        encoding="utf-8",
    )
    (tmp_path / "scorer.py").write_text(
        """
from snowl.core import Score
class S:
    scorer_id = "s1"
    def score(self, task_result, trace, context):
        _ = (task_result, trace, context)
        return {"accuracy": Score(value=1.0 if task_result.status.value == "success" else 0.0)}
scorer = S()
""",
        encoding="utf-8",
    )


def test_agent_variant_contract_validation() -> None:
    class A:
        agent_id = "a"

        async def run(self, state, context, tools=None):
            return state

    ok = make_agent_variant(agent=A(), agent_id="a", variant_id="v1", model="m")
    assert isinstance(ok, AgentVariant)

    try:
        make_agent_variant(agent=A(), agent_id="", variant_id="v1")
        raise AssertionError("expected validation error")
    except SnowlValidationError:
        pass


def test_variant_discovery_and_filter_and_artifacts(tmp_path: Path) -> None:
    _write_task_and_scorer(tmp_path)
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason, make_agent_variant

class VAgent:
    def __init__(self, v, m):
        self.agent_id = "chat"
        self.v = v
        self.m = m
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {
            "message": {"role":"assistant", "content": self.v},
            "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state

agent_variants = [
    make_agent_variant(agent=VAgent("v1", "m1"), agent_id="chat", variant_id="v1", model="m1"),
    make_agent_variant(agent=VAgent("v2", "m2"), agent_id="chat", variant_id="v2", model="m2"),
]
""",
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path, renderer=None, variant_filter=["v2"]))
    assert result.summary.total == 1
    out = result.outcomes[0]
    assert out.task_result.payload.get("variant_id") == "v2"
    assert out.task_result.payload.get("model") == "m2"

    aggregate = json.loads((Path(result.artifacts_dir) / "aggregate.json").read_text(encoding="utf-8"))
    matrix = aggregate["matrix"]["t1"]
    assert "chat#v2" in matrix


def test_large_variant_sweep_failure_isolation(tmp_path: Path) -> None:
    _write_task_and_scorer(tmp_path)
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason, make_agent_variant

class VAgent:
    def __init__(self, v, fail=False):
        self.agent_id = "chat"
        self.v = v
        self.fail = fail
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        if self.fail:
            raise RuntimeError(f"boom-{self.v}")
        state.output = {
            "message": {"role":"assistant", "content": self.v},
            "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state

agent_variants = [
    make_agent_variant(agent=VAgent(f"v{i}", fail=(i==7)), agent_id="chat", variant_id=f"v{i}", model=f"m{i}")
    for i in range(20)
]
""",
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path, renderer=None, max_running_trials=4))
    assert result.summary.total == 20
    assert result.summary.error == 1
    assert result.summary.success == 19

    diagnostics = json.loads((Path(result.artifacts_dir) / "diagnostics_index.json").read_text(encoding="utf-8"))
    assert any(row.get("variant_id") == "v7" for row in diagnostics)


def test_cli_variant_filter_works(tmp_path: Path) -> None:
    _write_task_and_scorer(tmp_path)
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason, make_agent_variant

class VAgent:
    def __init__(self, v):
        self.agent_id = "chat"
        self.v = v
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {"message": {"role":"assistant", "content": self.v}, "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2}, "trace_events": []}
        state.stop_reason = StopReason.COMPLETED
        return state

agent_variants = [
    make_agent_variant(agent=VAgent("v1"), agent_id="chat", variant_id="v1", model="m1"),
    make_agent_variant(agent=VAgent("v2"), agent_id="chat", variant_id="v2", model="m2"),
]
""",
        encoding="utf-8",
    )
    rc = main(["eval", str(tmp_path), "--variant", "v1", "--no-ui"])
    assert rc == 0


def test_cli_variant_filter_works_with_project_model_matrix(tmp_path: Path) -> None:
    _write_task_and_scorer(tmp_path)
    (tmp_path / "project.yml").write_text(
        """
project:
  name: matrix-demo
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-test
  timeout: 8
  max_retries: 1
agent_matrix:
  models:
    - id: alpha
      model: model-alpha
    - id: beta
      model: model-beta
judge:
  model: judge-model
eval:
  benchmark: custom
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
        """,
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from pathlib import Path

from snowl.agents import build_model_variants
from snowl.core import StopReason, agent


class VAgent:
    def __init__(self, model_name):
        self.model_name = model_name

    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {
            "message": {"role": "assistant", "content": self.model_name},
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state


def _factory(model_entry, provider):
    _ = provider
    return VAgent(model_entry.model)


@agent(agent_id="chat")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="chat",
        factory=_factory,
    )
""",
        encoding="utf-8",
    )

    rc = main(["eval", str(tmp_path), "--variant", "beta", "--no-ui", "--no-web-monitor"])
    assert rc == 0

    run_roots = sorted((tmp_path / ".snowl" / "runs" / "by_run_id").iterdir())
    latest = run_roots[-1]
    aggregate = json.loads((latest / "aggregate.json").read_text(encoding="utf-8"))
    matrix = aggregate["matrix"]["t1"]
    assert "chat#beta" in matrix
    assert "chat#alpha" not in matrix
