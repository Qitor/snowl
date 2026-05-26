"""Tier 1 E2E tests: core eval lifecycle with real LLM calls.

E2E-1: ChatAgent + IncludesScorer → TrialOutcome
E2E-2: Solver chain → TrialOutcome
E2E-3: ReActAgent with tool → tool execution observed
E2E-4: CLI `snowl eval` → artifacts produced
"""

from __future__ import annotations

import pytest

from snowl.core.env import EnvSpec
from snowl.core.task import Task
from snowl.runtime.engine import TrialRequest, execute_trial
from snowl.scorer import includes
from snowl.agents.chat_agent import ChatAgent

from .conftest import track_usage


# ---------------------------------------------------------------------------
# E2E-1: Single-turn ChatAgent eval
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.flaky(reruns=3, reruns_delay=5)
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_chat_agent_single_turn(live_client, cost_tracker):
    """ChatAgent + IncludesScorer: full eval from task to scored outcome."""
    task = Task(
        task_id="e2e-1",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([
            {"id": "s1", "input": "What is 2+2? Answer with just the number.",
             "metadata": {"target": "4"}},
        ]),
    )
    agent = ChatAgent(live_client, default_generation_kwargs={"max_tokens": 256})
    sample = {
        "id": "s1",
        "input": "What is 2+2? Answer with just the number.",
        "metadata": {"target": "4"},
    }

    outcome = await execute_trial(TrialRequest(
        task=task, agent=agent, sample=sample, scorer=includes(),
    ))

    # Structural assertions (not content-dependent)
    assert outcome.task_result.status.value in {"success", "incorrect"}
    assert outcome.task_result.final_output is not None
    assert isinstance(outcome.task_result.final_output, dict)
    assert outcome.task_result.usage is not None
    assert outcome.task_result.usage.total_tokens > 0
    assert outcome.task_result.timing is not None
    assert outcome.task_result.timing.duration_ms > 0
    assert "includes" in outcome.scores
    assert outcome.scores["includes"].value in {0.0, 1.0}

    track_usage(cost_tracker, outcome.task_result.usage)


# ---------------------------------------------------------------------------
# E2E-2: Solver chain eval
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.flaky(reruns=3, reruns_delay=5)
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_solver_chain_eval(live_client, cost_tracker):
    """chain(system_message, submit_tool, generate) produces a complete outcome."""
    from snowl.core.solver import chain
    from snowl.solver import system_message, submit_tool, generate

    solver = chain(
        system_message("You are a helpful assistant. Be very brief."),
        submit_tool(),
        generate(live_client, max_steps=2, generation_kwargs={"max_tokens": 256}),
    )

    task = Task(
        task_id="e2e-2",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([
            {"id": "s1", "input": "Say hello in one word.",
             "metadata": {"target": "hello"}},
        ]),
    )
    agent = ChatAgent(live_client)  # overridden by solver_chain
    sample = {
        "id": "s1",
        "input": "Say hello in one word.",
        "metadata": {"target": "hello"},
    }

    outcome = await execute_trial(TrialRequest(
        task=task, agent=agent, sample=sample, scorer=includes(),
        solver_chain=solver,
    ))

    assert outcome.task_result.status.value in {"success", "incorrect"}
    assert outcome.task_result.usage is not None
    assert outcome.task_result.usage.total_tokens > 0
    # Solver chain should have produced trace events
    trace_events = outcome.trace.get("trace_events", [])
    assert len(trace_events) > 0

    track_usage(cost_tracker, outcome.task_result.usage)


# ---------------------------------------------------------------------------
# E2E-3: Tool-calling eval with ReActAgent
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.flaky(reruns=3, reruns_delay=5)
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_react_agent_with_tool(live_client, cost_tracker):
    """ReActAgent + echo tool → tool execution observed in actions."""
    from snowl.core.tool import build_tool_spec
    from snowl.agents.react_agent import ReActAgent

    def echo(text: str) -> str:
        return text

    echo_spec = build_tool_spec(echo)

    task = Task(
        task_id="e2e-3",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([
            {"id": "s1", "input": "Use the echo tool to repeat the word 'test'."},
        ]),
    )
    agent = ReActAgent(
        live_client, max_steps=4, temperature=0.1,
        default_generation_kwargs={"max_tokens": 512},
    )
    sample = {"id": "s1", "input": "Use the echo tool to repeat the word 'test'."}

    outcome = await execute_trial(TrialRequest(
        task=task, agent=agent, sample=sample, scorer=includes(),
        tools=[echo_spec],
    ))

    assert outcome.task_result.status.value in {"success", "incorrect", "limit_exceeded"}
    actions = outcome.trace.get("actions", [])
    # The ReAct loop should have executed at least one step
    assert len(actions) >= 1, f"Expected >= 1 action, got {len(actions)}"

    track_usage(cost_tracker, outcome.task_result.usage)


# ---------------------------------------------------------------------------
# E2E-4: CLI `snowl eval` produces artifacts
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.flaky(reruns=3, reruns_delay=5)
@pytest.mark.timeout(180)
def test_cli_eval_produces_artifacts(live_config, tmp_path, cost_tracker):
    """Full CLI flow: snowl eval → artifacts produced on disk."""
    from .conftest import write_live_project
    from snowl.cli import main

    write_live_project(tmp_path, live_config)

    rc = main(["eval", str(tmp_path / "project.yml")])
    assert rc == 0

    # Verify artifacts directory
    runs_dir = tmp_path / ".snowl" / "runs"
    assert runs_dir.exists(), "No .snowl/runs directory created"

    # Find actual run directories (skip by_run_id which is an index)
    run_dirs = sorted([
        d for d in runs_dir.iterdir()
        if d.is_dir() and d.name != "by_run_id" and (d / "outcomes.json").exists()
    ])
    assert len(run_dirs) >= 1, "No run directories with outcomes.json found"

    latest = run_dirs[-1]
    outcomes_file = latest / "outcomes.json"
    assert outcomes_file.exists(), f"No outcomes.json in {latest}"
