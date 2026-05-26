# Snowl

[![CI](https://github.com/Qitor/snowl/actions/workflows/ci.yml/badge.svg)](https://github.com/Qitor/snowl/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![Benchmarks](https://img.shields.io/badge/benchmarks-25%2B-success)
[![Docs](https://img.shields.io/badge/docs-site-blue)](https://qitor.github.io/snowl)
[English](./README.md) | [简体中文](./README.zh-CN.md)

**Snowl** is a framework-agnostic evaluation engine for AI agents. Run any agent against any benchmark, get reproducible scores, and compare fairly — in 3 lines of code.

```python
from snowl import quick_eval

result = quick_eval(
    agent=lambda prompt: "I cannot help with that.",
    benchmark="strongreject",
    limit=10,
)
print(f"Pass rate: {result.pass_rate:.0%}  Cost: {result.total_tokens} tokens")
```

## Install

```bash
pip install snowl
```

With framework support:

```bash
pip install snowl[qitos]       # QitOS agents
pip install snowl[langgraph]   # LangGraph agents
pip install snowl[openai]      # OpenAI Agents SDK
```

## 30-Second Tour

**Python API** — evaluate any callable:

```python
from snowl import quick_eval

# Evaluate a simple function
result = quick_eval(
    agent=lambda prompt: "hello",
    samples=[{"id": "s1", "input": "Say hi", "target": "hello"}],
    scorer="includes",
)

# Evaluate against a built-in benchmark
result = quick_eval(agent=my_async_fn, benchmark="bfcl", limit=50)
```

**CLI** — run full evaluation projects:

```bash
snowl bench list                                    # list benchmarks
snowl eval project.yml                              # run eval
snowl bench run strongreject --split test --limit 10  # run benchmark
snowl retry run-20260427T120000Z                    # retry failures
```

## Why Snowl

| Problem | Snowl's Answer |
|---------|---------------|
| Agents are hard to plug into benchmarks | 3-line `quick_eval()` + Adapter SDK (QitOS, LangGraph, OpenAI Agents) |
| Safety evaluation is shallow | Built-in scorers: canary leak, tool trace policy, workspace diff, command check, injection |
| Scores aren't comparable across models | Cost-aware scoring, separated verifier, working-time metrics |
| Runs are hard to reproduce | Deterministic Task x AgentVariant x Sample planning, full artifact trail |
| Terminal/GUI/web tasks behave differently | Phase-aware runtime with Docker sandbox, container isolation, AIMD flow control |

## Core Concepts

```text
Task × Agent × Scorer → TrialOutcome → Aggregated Result
```

- **Task**: what to evaluate (samples + environment spec)
- **Agent**: what is being evaluated (any Python callable or Agent Protocol)
- **Scorer**: how to judge (15+ built-in: includes, match, model-as-judge, canary, tool trace, ...)
- **Runtime**: where it runs (local, Docker sandbox, GUI container)

## Built-in Benchmarks

25+ benchmarks across safety and capability:

| Category | Benchmarks |
|----------|-----------|
| Safety | StrongReject, XSTest, AgentHarm, CoConot, FORTRESS, MASK, SevenLLM |
| Cybersecurity | WMDP, CyberMetric, SecQA, CyBench, CyberGym |
| Tool Use / Agent | BFCL, AgentDojo, AgentBench-OS, ToolEmu, IPI Coding Agent |
| Capability | GAIA, Tau-Bench, OSWorld, TerminalBench, SWE-Bench, HumanEval |
| Custom | JSONL, CSV adapters for your own datasets |

## What You Get From Each Run

Every run produces a self-contained artifact directory:

```text
.snowl/runs/<run_id>/
  outcomes.json          # per-sample results
  aggregate.json         # summary metrics
  events.jsonl           # full event stream
  leaderboard_rows.jsonl # ranked results
  recovery.json          # retry state
```

## Documentation

- [Getting Started](https://qitor.github.io/snowl/getting-started/)
- [Tutorials](https://qitor.github.io/snowl/tutorials/)
- [API Reference](https://qitor.github.io/snowl/api-reference/)
- [Architecture](https://qitor.github.io/snowl/architecture/)

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## Contributing

Snowl needs contributors who care about making AI agents safer and easier to measure. Good first areas:

- Add a benchmark adapter
- Improve a scorer
- Write a framework adapter (CrewAI, AutoGen, PydanticAI)
- Add docs for a real evaluation workflow

## License

See the repository license file.
