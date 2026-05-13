# Snowl

Open-source safety evaluation framework for AI agents.

Snowl helps you run reproducible, observable, and retryable evaluations across
agent implementations, model variants, benchmarks, and execution environments.
Think of it as a local *wind tunnel* for agent safety testing: define what an
agent should do, run it against realistic tasks, capture every artifact, and
compare results — without rebuilding the whole evaluation stack each time.

---

## Why Snowl?

Most agent evaluation projects hit the same wall:

- Every benchmark has its own runner
- Agents are hard to plug into other people's tests
- Test sets become stale
- Terminal, GUI, web, and local tasks all behave differently
- Failures are difficult to reproduce
- Dashboards show scores but not what actually happened

Snowl turns those pieces into one framework:

- A small **Task / Agent / Scorer** contract
- Deterministic **Task × AgentVariant × Sample** planning
- Built-in adapters for popular safety and capability suites
- Runtime budgets for model calls, containers, builds, and scoring
- Live run artifacts under `.snowl/runs/<run_id>/`
- Retry and recovery ledgers for long-running evaluations
- A local web monitor for runs, traces, risk rollups, and benchmark views

---

## Quick links

| If you want to... | Go to |
|---|---|
| Install and run your first eval | [Getting Started](getting-started/index.md) |
| Learn the project structure and core concepts | [Tutorials](tutorials/index.md) |
| Solve a specific problem | [How-to Guides](how-to/index.md) |
| Browse available benchmarks | [Benchmark Catalog](benchmarks/index.md) |
| Look up a class or function signature | [API Reference](api-reference/index.md) |
| Understand the runtime architecture | [Architecture](architecture/index.md) |

---

## The core contract in 30 seconds

Every Snowl evaluation project is four files:

```
my-project/
  project.yml    # Configuration: provider, models, benchmark, runtime
  agent.py       # Agent definition: how the agent is constructed
  task.py        # Task definition: what benchmark to load
  scorer.py      # Scorer definition: how to score agent outputs
```

An agent is any object with `agent_id` and `async def run()`:

```python
class MyAgent:
    agent_id = "my-agent"

    async def run(self, state, context, tools=None):
        state.output = {"message": "I cannot help with that."}
        state.stop_reason = "completed"
        return state
```

A scorer evaluates agent output:

```python
class SafetyScorer:
    scorer_id = "safety"

    def score(self, task_result, trace, context):
        content = task_result.final_output.get("message", {}).get("content", "")
        return {"refusal": Score(value=1.0 if "cannot" in content.lower() else 0.0)}
```

Run it:

```bash
snowl eval ./project.yml
```

That's it. Snowl handles planning, execution, scoring, artifact persistence,
and recovery.

---

## Current highlights

- **YAML-first** project entrypoint with `project.yml`
- **Multi-model sweeps** through `agent_matrix.models`
- **28 built-in benchmark adapters** spanning agent safety, capability, and
  cybersecurity domains
- **Built-in scorer primitives**: answer matching, function-call matching, tool
  trace policy, canary leakage, workspace/state checks, command checks,
  checkpoint scoring, rubric judging, and grouped metrics
- **Tool middleware** for composable interception of tool calls and results
- **LM-emulated tool execution** via `EmulatedToolWrapper` (ToolEmu-style)
- **Stateful tool execution** via `StatefulToolExecutor` (AgentDojo-style)
- **Phase-aware runtime** with concurrency controls and provider budgets
- **Automatic run artifacts**: manifest, plan, events, outcomes, aggregates,
  CSV exports, and recovery ledgers
- **Retry and recovery**: `snowl retry <run_id>` plus deferred in-run auto retry
- **Rich TUI** with colored panels and progress bars
- **Web monitor** for live run observability
