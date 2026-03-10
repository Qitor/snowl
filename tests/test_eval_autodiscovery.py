from __future__ import annotations

import asyncio
import os
from pathlib import Path

from snowl.eval import run_eval


def test_run_eval_auto_discovers_tool_py(tmp_path: Path) -> None:
    (tmp_path / "tool.py").write_text(
        """
from snowl.core import tool

@tool
+def echo(text: str) -> str:
+    \"\"\"Echo input text.\"\"\"
+    return text
        """.replace("+", ""),
        encoding="utf-8",
    )

    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task


def _samples():
    yield {"id": "s1", "input": "hello"}


task = Task(
    task_id="t1",
    env_spec=EnvSpec(env_type="local"),
    sample_iter_factory=_samples,
)
        """,
        encoding="utf-8",
    )

    (tmp_path / "agent.py").write_text(
        """
from snowl.core import AgentState, StopReason

class ToolAwareAgent:
    agent_id = "tool-aware"

    async def run(self, state, context, tools=None):
        tool_names = [t.name for t in (tools or [])]
        state.output = {
            "message": {"role": "assistant", "content": "ok"},
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            "trace_events": [{"event": "agent.run", "tool_names": tool_names}],
        }
        state.stop_reason = StopReason.COMPLETED
        return state

agent = ToolAwareAgent()
        """,
        encoding="utf-8",
    )

    (tmp_path / "scorer.py").write_text(
        """
from snowl.core import Score

class BasicScorer:
    scorer_id = "basic"

    def score(self, task_result, trace, context):
        names = trace.get("trace_events", [{}])[-1].get("tool_names", [])
        return {"accuracy": Score(value=1.0 if "echo" in names else 0.0)}

scorer = BasicScorer()
        """,
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path))

    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.task_result.status.value == "success"
    assert outcome.scores["accuracy"].value == 1.0


def test_run_eval_uses_project_yml_as_formal_entry(tmp_path: Path) -> None:
    (tmp_path / "project.yml").write_text(
        """
project:
  name: demo
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-test
  timeout: 12
  max_retries: 1
agent_matrix:
  models:
    - id: tested_model
      model: tested-model
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

    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task
task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1","input":"x"}]))
        """,
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from pathlib import Path
from snowl.core import StopReason
from snowl.project_config import load_project_config

class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        project = load_project_config(Path(__file__).parent)
        state.output = {
            "message": {"role": "assistant", "content": project.judge.model if project.judge else ""},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state

agent = A()
        """,
        encoding="utf-8",
    )
    (tmp_path / "scorer.py").write_text(
        """
from snowl.core import Score

class S:
    scorer_id = "s1"
    def score(self, task_result, trace, context):
        ok = (task_result.final_output.get("content") == "judge-model")
        return {"accuracy": Score(value=1.0 if ok else 0.0)}

scorer = S()
        """,
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path / "project.yml"))
    assert result.summary.success == 1
    assert result.outcomes[0].task_result.final_output.get("content") == "judge-model"


def test_project_yml_is_source_of_truth_for_provider_config(tmp_path: Path) -> None:
    (tmp_path / "project.yml").write_text(
        """
project:
  name: demo
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-fixed
agent_matrix:
  models:
    - id: tested_model
      model: tested-model
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
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task
task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1","input":"x"}]))
        """,
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from pathlib import Path
from snowl.core import StopReason
from snowl.project_config import load_project_config
class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        project = load_project_config(Path(__file__).parent)
        state.output = {
            "message": {"role": "assistant", "content": project.provider.api_key},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state
agent = A()
        """,
        encoding="utf-8",
    )
    (tmp_path / "scorer.py").write_text(
        """
from snowl.core import Score
class S:
    scorer_id = "s1"
    def score(self, task_result, trace, context):
        ok = task_result.final_output.get("content", "").startswith("sk-")
        return {"accuracy": Score(value=1.0 if ok else 0.0)}
scorer = S()
        """,
        encoding="utf-8",
    )
    result = asyncio.run(run_eval(tmp_path / "project.yml"))
    assert result.summary.success == 1
    assert result.outcomes[0].task_result.final_output.get("content") == "sk-fixed"


def test_run_eval_expands_agent_matrix_variants(tmp_path: Path) -> None:
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
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task

task = Task(
    task_id="t1",
    env_spec=EnvSpec(env_type="local"),
    sample_iter_factory=lambda: iter([{"id": "s1", "input": "x"}]),
)
        """,
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from pathlib import Path

from snowl.agents import build_model_variants
from snowl.core import StopReason, agent


class ModelAwareAgent:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def run(self, state, context, tools=None):
        state.output = {
            "message": {"role": "assistant", "content": self.model_name},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state


def _factory(model_entry, provider):
    _ = provider
    return ModelAwareAgent(model_entry.model)


@agent(agent_id="matrix_agent")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="matrix_agent",
        factory=_factory,
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
        return {"accuracy": Score(value=1.0)}


scorer = S()
        """,
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path / "project.yml"))
    assert len(result.outcomes) == 2
    models = sorted(str((outcome.task_result.payload or {}).get("model") or "") for outcome in result.outcomes)
    assert models == ["model-alpha", "model-beta"]
