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


def test_run_eval_loads_model_yml_into_env(tmp_path: Path, monkeypatch) -> None:
    for key in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_TIMEOUT", "OPENAI_MAX_RETRIES"):
        monkeypatch.delenv(key, raising=False)

    (tmp_path / "model.yml").write_text(
        """
provider:
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
import os
from snowl.core import StopReason

class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        state.output = {
            "message": {"role": "assistant", "content": os.getenv("OPENAI_MODEL", "")},
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

    result = asyncio.run(run_eval(tmp_path))
    assert result.summary.success == 1
    assert os.environ.get("OPENAI_MODEL") == "judge-model"


def test_model_yml_overrides_whitespace_env_value(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    (tmp_path / "model.yml").write_text(
        """
provider:
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-fixed
agent_matrix:
  models:
    - id: tested_model
      model: tested-model
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
import os
from snowl.core import StopReason
class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        state.output = {
            "message": {"role": "assistant", "content": os.getenv("OPENAI_API_KEY", "")},
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
    result = asyncio.run(run_eval(tmp_path))
    assert result.summary.success == 1
    assert os.environ.get("OPENAI_API_KEY") == "sk-fixed"


def test_run_eval_expands_agent_matrix_variants(tmp_path: Path) -> None:
    (tmp_path / "model.yml").write_text(
        """
provider:
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

    result = asyncio.run(run_eval(tmp_path))
    assert len(result.outcomes) == 2
    models = sorted(str((outcome.task_result.payload or {}).get("model") or "") for outcome in result.outcomes)
    assert models == ["model-alpha", "model-beta"]
