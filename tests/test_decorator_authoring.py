from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from snowl.errors import SnowlValidationError
from snowl.eval import run_eval


def test_decorator_factory_discovery_with_fallback_compat(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task, task

@task()
def task_factory():
    return Task(
        task_id="t1",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([{"id":"s1", "input":"x"}]),
    )
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason, agent

class A:
    def __init__(self, agent_id, content):
        self.agent_id = agent_id
        self._content = content
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {
            "message": {"role":"assistant", "content": self._content},
            "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state

@agent()
def decorated_agents():
    return [A("a1", "decorated")]

fallback_agent = A("a2", "fallback")
""",
        encoding="utf-8",
    )
    (tmp_path / "scorer.py").write_text(
        """
from snowl.core import Score, scorer

class S:
    scorer_id = "s1"
    def score(self, task_result, trace, context):
        _ = (trace, context)
        ok = task_result.final_output.get("content") in {"decorated", "fallback"}
        return {"accuracy": Score(value=1.0 if ok else 0.0)}

@scorer()
def scorer_factory():
    return S()
""",
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path, renderer=None))
    assert result.summary.total == 2
    assert result.summary.success == 2
    assert sorted(result.plan.agent_ids) == ["a1", "a2"]


def test_mixed_mode_duplicate_ids_raise_actionable_error(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task, task

@task()
def decorated_task():
    return Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1","input":"x"}]))

fallback_task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s2","input":"y"}]))
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason
class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {"message": {"role":"assistant", "content":"ok"}, "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2}, "trace_events": []}
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
        _ = (task_result, trace, context)
        return {"accuracy": Score(value=1.0)}
scorer = S()
""",
        encoding="utf-8",
    )

    with pytest.raises(SnowlValidationError, match="Duplicate task_id 't1'"):
        asyncio.run(run_eval(tmp_path, renderer=None))


def test_strict_id_mode_rejects_fallback_objects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNOWL_DISCOVERY_STRICT_IDS", "1")
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task
task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1","input":"x"}]))
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason
class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {"message": {"role":"assistant", "content":"ok"}, "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2}, "trace_events": []}
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
        _ = (task_result, trace, context)
        return {"accuracy": Score(value=1.0)}
scorer = S()
""",
        encoding="utf-8",
    )

    with pytest.raises(SnowlValidationError, match="SNOWL_DISCOVERY_STRICT_IDS=1"):
        asyncio.run(run_eval(tmp_path, renderer=None))
