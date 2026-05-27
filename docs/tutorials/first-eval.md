# Your First Evaluation

Run your first Snowl evaluation in under 5 minutes.

---

## Prerequisites

- Python 3.10+
- An OpenAI API key (or any OpenAI-compatible endpoint)

## Install

```bash
pip install snowl
pip install snowl-evals  # benchmark library
```

## Set your API key

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4.1-mini"
```

## Run a quick evaluation

The fastest way to evaluate an agent is `quick_eval_sync()`:

```python
from snowl import quick_eval_sync

result = quick_eval_sync(
    agent=lambda msgs, tools: "I cannot help with that.",
    benchmark="strongreject",
    limit=5,
    scorer="includes",
)

print(result)
```

Output:

```
QuickEvalResult: 20% pass rate (5 samples)
  Status: mixed
  Scores: {'includes': 0.2}
  Tokens: 0  Duration: 1203ms  Working: 845ms
  Cost: $0.0023
  Score/$: 86.96
```

## Understanding the result

| Field | Meaning |
|-------|---------|
| `pass_rate` | Fraction of samples that passed |
| `status` | `success`, `incorrect`, `mixed`, or `error` |
| `scores` | Per-metric averages |
| `duration_ms` | Wall-clock time for all trials |
| `working_time_ms` | Agent execution time (excludes scoring, wait) |
| `estimated_cost_usd` | Total estimated API cost |
| `score_per_dollar` | Primary score / cost (efficiency) |
| `first_error` | First exception message, if any trials failed |

## Using a real agent

Replace the lambda with a function that calls an LLM:

```python
from snowl.model.openai_compatible import OpenAICompatibleChatClient, OpenAICompatibleConfig

config = OpenAICompatibleConfig(
    base_url="https://api.openai.com/v1",
    api_key="sk-...",
    model="gpt-4.1-mini",
)
client = OpenAICompatibleChatClient(config)

async def my_agent(messages, tools):
    import asyncio
    resp = await client.generate(messages)
    return resp.message.get("content", "")

from snowl import quick_eval

result = await quick_eval(
    agent=my_agent,
    benchmark="xstest",
    limit=10,
)
print(result)
```

## Framework-specific wrappers

Snowl provides convenience wrappers for common frameworks:

```python
from snowl import quick_eval_qitos, quick_eval_langgraph, quick_eval_openai

# QitOS
result = await quick_eval_qitos(agent_module=my_agent, benchmark="cybench", limit=5)

# LangGraph
result = await quick_eval_langgraph(graph=compiled_graph, benchmark="gaia", limit=5)

# OpenAI Agents
result = await quick_eval_openai(client=openai_client, benchmark="xstest", limit=5)
```

## Custom samples

You can evaluate against your own data without a benchmark:

```python
result = quick_eval_sync(
    agent=lambda msgs, tools: "hello",
    samples=[
        {"id": "s1", "input": "Say hi", "target": "hello"},
        {"id": "s2", "input": "Say bye", "target": "goodbye"},
    ],
    scorer="includes",
)
```

## Next steps

- [Writing a Scorer](writing-a-scorer.md) -- customize how outputs are graded
- [Scoring Deep Dive](scoring-deep-dive.md) -- cost efficiency, LLM judges, normalization
- [Runtime](runtime.md) -- concurrency, middleware, container providers
- [CLI](cli.md) -- running evaluations from the command line
