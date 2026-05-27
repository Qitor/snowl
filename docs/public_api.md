# Public API Reference

Snowl's public API — the stable surface you can rely on across minor versions.

---

## Stability Guarantee

Symbols re-exported from `snowl` and `snowl.core` are the **public API**. Changes follow semantic versioning:
- **Minor versions**: New symbols may be added; existing signatures will not break.
- **Major versions**: Symbols may be removed or renamed with a migration path.

Internal modules (prefixed with `_` or not re-exported) may change without notice.

## Top-Level Imports

```python
from snowl import (
    # Version
    __version__,

    # Quick evaluation
    quick_eval,
    quick_eval_sync,
    quick_eval_qitos,
    quick_eval_langgraph,
    quick_eval_openai,
    QuickEvalResult,

    # Core types
    Task, Agent, Scorer, Score, ScoreContext, TaskResult,
    EnvSpec, SandboxSpec, ToolSpec, AgentState, AgentContext,

    # Agents
    ReActAgent,
    ChatAgent,

    # Model client
    OpenAICompatibleChatClient,
    OpenAICompatibleConfig,
    load_openai_compatible_config,

    # Runtime
    TrialLimits,
    TrialOutcome,
    TrialRequest,
    execute_trial,

    # Registry
    SnowlRegistry,
    get_registry,

    # Scorers
    includes,
    match,
    model_as_judge_json,
    pattern,

    # Canary
    strip_canary,
    strip_canary_from_sample,

    # Errors
    SnowlValidationError,
)
```

## Core Layer (`snowl.core`)

| Module | Key Types |
|--------|-----------|
| `snowl.core.task` | `Task`, `TaskProvider` |
| `snowl.core.agent` | `Agent`, `AgentState`, `AgentContext` |
| `snowl.core.scorer` | `Scorer`, `AsyncScorer`, `Score`, `ScoreContext` |
| `snowl.core.tool` | `ToolSpec`, `ToolRegistry`, `build_tool_spec` |
| `snowl.core.env` | `EnvSpec`, `SandboxSpec` |
| `snowl.core.task_result` | `TaskResult`, `TaskStatus`, `Timing`, `Usage` |
| `snowl.core.declarations` | `@task`, `@agent`, `@scorer`, `@tool` decorators |
| `snowl.core.agent_variant` | `AgentVariant` |

The core layer has **zero third-party dependencies** and **never imports from adapter packages**.

## Scorer Module (`snowl.scorer`)

| Scorer | Purpose |
|--------|---------|
| `includes` | Check if target string appears in output |
| `match` | Exact string match |
| `pattern` | Regex pattern match |
| `model_as_judge_json` | LLM-as-judge with structured JSON grading |
| `ToolTracePolicyScorer` | Score tool call compliance against policy |
| `CostNormalizedScorer` | Normalize score by estimated cost |
| `InjectionScoreMatrix` | Multi-dimensional injection safety scoring |

## Quick Evaluation

```python
result = quick_eval(
    agent=lambda prompt: "hello",
    benchmark="strongreject",
    limit=10,
)
# result.pass_rate, result.total_tokens, result.duration_ms
```

See [quick-start.md](./getting-started/quick-start.md) for the full walkthrough.
