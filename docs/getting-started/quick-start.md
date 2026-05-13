# Quick Start

Build and run your first evaluation project in under five minutes.

---

## 1. Install Snowl

```bash
pip install -e .
```

## 2. Run a built-in benchmark

The fastest way to see Snowl in action:

```bash
snowl eval examples/strongreject-official/project.yml --limit 5
```

You'll see a Rich-panel TUI with colored progress, model I/O, and scorer
results scrolling in your terminal.

## 3. Create your own project

Every Snowl evaluation project is a directory with four files:

```
my-project/
  project.yml    # Configuration
  agent.py       # Agent definition
  task.py        # Task definition
  scorer.py      # Scorer definition
```

### project.yml

```yaml
project:
  name: my-eval

provider:
  id: my-provider
  kind: openai_compatible
  base_url: https://api.example.com/v1
  api_key: sk-xxx
  timeout: 120

agent_matrix:
  models:
    - id: my_model
      model: my-model-v1
      metadata:
        company: acme
        source_type: open_source

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
  max_running_trials: 2
  provider_budgets:
    my-provider: 100
```

### task.py

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

### agent.py

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

### scorer.py

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

## 4. Run your project

```bash
snowl eval ./my-project/project.yml
```

## 5. Inspect results

Results are written to `.snowl/runs/<run_id>/`:

```bash
# View the aggregate metrics
cat .snowl/runs/<run_id>/aggregate.json

# View the HTML report
open .snowl/runs/<run_id>/report.html
```

---

## What's next?

- [Project Anatomy](../tutorials/project-anatomy.md) — understand every field in `project.yml`
- [Writing an Agent](../tutorials/writing-an-agent.md) — go beyond the default ReActAgent
- [Writing a Scorer](../tutorials/writing-a-scorer.md) — build custom evaluation logic
- [Benchmark Catalog](../benchmarks/index.md) — browse all available benchmarks
