# Project Anatomy

A Snowl evaluation project is a directory containing four files that together
define what to evaluate, how to run it, and how to score it.

---

## Directory structure

```
my-project/
  project.yml    # Configuration: provider, models, benchmark, runtime
  agent.py       # Agent definition: how the agent is constructed
  task.py        # Task definition: what benchmark to load
  scorer.py      # Scorer definition: how to score agent outputs
  tool.py        # Optional: custom tool definitions
```

## project.yml

The central configuration file and formal run entrypoint.

```yaml
project:
  name: my-eval
  root_dir: .

provider:
  id: my-provider
  kind: openai_compatible
  base_url: https://api.example.com/v1
  api_key: sk-xxx
  timeout: 120
  max_retries: 2

agent_matrix:
  models:
    - id: my_model
      model: my-model-v1
      metadata:
        company: acme
        source_type: open_source
    - id: gpt4o
      model: gpt-4o-2024-05-13
      provider:                    # Per-model provider override
        base_url: https://api.openai.com/v1
        api_key: sk-xxx

eval:
  benchmark: strongreject
  split: test
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
  limit: 10

runtime:
  max_running_trials: 4
  max_scoring_tasks: 4
  provider_budgets:
    my-provider: 8

judge:                               # Optional: LLM judge provider
  provider_id: openai
  model: gpt-4o-2024-05-13
  base_url: https://api.openai.com/v1
  api_key: sk-xxx
```

### Key sections

| Section | Purpose |
|---------|---------|
| `project` | Project name and root directory |
| `provider` | Default LLM API endpoint (OpenAI-compatible) |
| `agent_matrix.models` | List of model variants to evaluate |
| `eval` | Which benchmark, where the code is, sample limits |
| `runtime` | Concurrency limits and provider budgets |
| `judge` | Optional separate provider for LLM-based judging |

### Provider configuration

```yaml
provider:
  id: my-provider           # Unique provider identifier
  kind: openai_compatible   # Currently the only supported kind
  base_url: https://api.example.com/v1
  api_key: sk-xxx
  timeout: 120              # Request timeout in seconds
  max_retries: 2            # HTTP retry count for transient errors
```

Per-model provider overrides are supported:

```yaml
agent_matrix:
  models:
    - id: external_model
      model: gpt-4o
      provider:              # Overrides the top-level provider
        base_url: https://api.openai.com/v1
        api_key: sk-xxx
```

### Runtime controls

```yaml
runtime:
  max_running_trials: 4      # Max concurrent trial executions
  max_container_slots: 2     # Max concurrent container/sandbox slots
  max_builds: 2              # Max concurrent container builds
  max_scoring_tasks: 4       # Max concurrent scoring tasks
  provider_budgets:
    my-provider: 8           # Max concurrent model calls per provider
  recovery:                   # Optional: deferred auto retry
    retry_timing: deferred
    backoff_ms: 5000
    max_auto_retries_per_trial: 1
```

## agent.py

Defines the agent under test. The file must export agent objects that satisfy
the `Agent` protocol:

- `agent_id: str`
- `async def run(self, state, context, tools=None) -> AgentState`

For multi-model sweeps, use `build_model_variants` to expand a factory across
all models in `agent_matrix.models`:

```python
from pathlib import Path
from snowl.agents import ReActAgent, build_model_variants
from snowl.core import agent as declare_agent
from snowl.model import OpenAICompatibleChatClient, ProjectModelEntry, ProjectProviderConfig

PROJECT_DIR = Path(__file__).resolve().parent

def _build_react_agent(model_entry: ProjectModelEntry, provider: ProjectProviderConfig):
    client = OpenAICompatibleChatClient(model_entry.config)
    return ReActAgent(
        model_client=client,
        agent_id="react_agent",
        max_steps=10,
    )

@declare_agent(agent_id="react_agent")
def agents():
    return build_model_variants(
        base_dir=PROJECT_DIR,
        agent_id="react_agent",
        factory=_build_react_agent,
    )
```

See [Writing an Agent](writing-an-agent.md) for more patterns.

## task.py

Defines what benchmark samples to load:

```python
from pathlib import Path
from snowl.core import task as declare_task, Task
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
from snowl.benchmarks.example_task import load_single_task
from snowl.project_config import load_project_config

PROJECT = load_project_config(Path(__file__).parent)

@declare_task()
def task() -> Task:
    adapter = StrongRejectBenchmarkAdapter()
    return load_single_task(
        adapter,
        split=PROJECT.eval.split or "test",
        limit=PROJECT.eval.limit,
    )
```

See [Writing a Task](writing-a-task.md) for more patterns.

## scorer.py

Defines how agent outputs are evaluated:

```python
from snowl.core import Scorer, Score, ScoreContext, TaskResult

class MyScorer:
    scorer_id = "my_scorer"

    def score(self, task_result: TaskResult, trace: dict, context: ScoreContext) -> dict[str, Score]:
        output = task_result.final_output or ""
        is_safe = "dangerous" not in str(output).lower()
        return {
            "safety": Score(value=1.0 if is_safe else 0.0, explanation="Output safety check"),
        }

scorer = MyScorer()
```

See [Writing a Scorer](writing-a-scorer.md) for more patterns.

## tool.py (optional)

Custom tool definitions that extend the agent's available tools:

```python
from snowl.core import tool, ToolRegistry

registry = ToolRegistry()

@tool(registry=registry)
def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"
```

---

## How the four files connect

```
project.yml ─── loads ──→ agent.py, task.py, scorer.py
                               │          │          │
                               ▼          ▼          ▼
                          AgentVariant  Task     Scorer
                               │          │          │
                               └──────────┼──────────┘
                                          ▼
                                    Plan (Task × Agent × Sample)
                                          │
                                          ▼
                                    Trial Execution
                                          │
                                          ▼
                                    Run Artifacts
```

1. `project.yml` specifies which files to load and what models to evaluate
2. `task.py` loads benchmark samples into Snowl `Task` objects
3. `agent.py` constructs agents (one per model variant) for evaluation
4. `scorer.py` evaluates each trial's output
5. Snowl plans all (task × agent × sample) trials and executes them
6. Results are written to `.snowl/runs/<run_id>/`
