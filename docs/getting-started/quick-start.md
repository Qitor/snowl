# Quick Start

Evaluate any agent in 3 lines of code — no project.yml required.

---

## 1. Install

```bash
pip install snowl
```

With framework support:

```bash
pip install snowl[qitos]       # QitOS agents
pip install snowl[langgraph]   # LangGraph agents
pip install snowl[openai]      # OpenAI Agents SDK
```

## 2. Evaluate an Agent (Python API)

The simplest way to evaluate an agent is `quick_eval()`:

```python
from snowl import quick_eval

result = quick_eval(
    agent=lambda msgs, tools: "I cannot help with that.",
    benchmark="strongreject",
    limit=10,
)
print(result)
# QuickEvalResult: 80% pass rate (10 samples)
#   Status: incorrect
#   Scores: {'includes': 0.8}
#   Tokens: 0  Duration: 1205ms
```

`agent` can be:

- A **bare callable**: `lambda msgs, tools: "response"`
- An **async function**: `async def my_agent(messages, tools) -> str`
- An **Agent Protocol** instance: any object with `agent_id` and `async run(state, context, tools)`

`scorer` can be a string name or a Scorer instance:

```python
result = quick_eval(agent=my_fn, samples=my_samples, scorer="match")
result = quick_eval(agent=my_fn, benchmark="bfcl", scorer=my_custom_scorer)
```

## 3. Evaluate via CLI

```bash
# List available benchmarks
snowl bench list

# Run a built-in benchmark
snowl bench run strongreject --project project.yml --split test --limit 10

# Run a full evaluation project
snowl eval project.yml

# Retry failed trials
snowl retry run-20260427T120000Z
```

## 4. Create an Evaluation Project

For more control, create a project directory:

```
my-project/
  project.yml    # Configuration (provider, models, runtime)
  agent.py       # Agent definition
  task.py        # Task definition
  scorer.py      # Scorer definition
```

Minimal `project.yml`:

```yaml
project:
  name: my-eval

provider:
  id: default
  kind: openai_compatible
  base_url: https://api.openai.com/v1
  api_key: sk-xxx

agent_matrix:
  models:
    - id: gpt4o-mini
      model: gpt-4o-mini

eval:
  benchmark: strongreject
  split: test
  limit: 10

runtime:
  max_running_trials: 4
```

Run it:

```bash
snowl eval ./my-project/project.yml
```

## 5. Inspect Results

Results are written to `.snowl/runs/<run_id>/`:

```bash
cat .snowl/runs/<run_id>/outcomes.json    # per-sample results
cat .snowl/runs/<run_id>/aggregate.json   # summary metrics
```

---

## Next Steps

- [Project Anatomy](../tutorials/project-anatomy.md) — understand every field in `project.yml`
- [Writing an Agent](../tutorials/writing-an-agent.md) — advanced agent patterns
- [Writing a Scorer](../tutorials/writing-a-scorer.md) — custom evaluation logic
- [Benchmark Catalog](../benchmarks/index.md) — browse all available benchmarks
