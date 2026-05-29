# Design Principles

Snowl's architecture follows these core principles:

## Evaluation-Only, Not Development

Snowl is a **specialized evaluation framework**, not a general-purpose agent development framework. The boundary is:

| Snowl Does | Snowl Does NOT |
|-----------|---------------|
| Evaluation pipeline scheduling (Task x AgentVariant x Sample → Scorer → Aggregation) | Agent execution loops (use QitOS / LangGraph / OpenAI Agents) |
| Minimal agent integration (3 lines of code to connect any agent) | Build another agent development framework |
| Security evaluation depth (canary / tool trace / workspace diff / injection) | General agent capability building |
| Scoring science (separated verification / multi-judge / PassAtK / cost fairness) | Model interaction protocol details |
| Benchmark data layer (snowl-evals plugin) | Runtime logic and container management |

## Core Layer Independence

The `snowl/core/` package must stay framework-independent:

- No third-party imports in core/
- No imports from adapters, benchmarks, model, runtime, or tools
- Adapters depend on core, never the reverse
- New integrations are added as adapters, not by modifying core contracts

## Agent Protocol Simplicity

The `Agent` protocol requires only:

```python
class Agent:
    agent_id: str
    async def run(self, state, context, tools=None) -> AgentState
```

Any Python async function can become a Snowl agent via `quick_eval()`:

```python
from snowl import quick_eval
result = quick_eval(agent=lambda prompt: "response", benchmark="strongreject")
```

## Plugin Discovery

Snowl uses Python `entry_points` for plugin discovery:

- **Benchmarks**: `snowl.benchmarks` entry point group
- **Adapters**: `snowl.adapters` entry point group
- **Container Providers**: `snowl.container_providers` entry point group

Third-party packages register via `pyproject.toml` — no modifications to Snowl needed.

## Scoring Integrity

- **Separated verification**: Verifiers run in isolated containers, preventing agent tampering
- **Cost-aware comparison**: Scores are normalized by cost for fair model comparison
- **Working time separation**: Rate-limit wait time is excluded from evaluation timing
- **Canary stripping**: Evaluation data markers are auto-removed before agent sees them

## Public API Stability

Symbols exported from `snowl.core.__all__` and `snowl.__all__` are the public API. Changes must:

1. Have regression tests
2. Follow deprecation cycle (version-tagged `DeprecationWarning`)
3. Not break existing project.yml configurations
