# Compatibility

Supported Python versions, dependency requirements, and versioning policy.

---

## Python Version

Snowl requires **Python 3.10+**.

## Installation Variants

| Package | Command | What you get |
|---------|---------|-------------|
| Core | `pip install snowl` | `quick_eval()`, built-in benchmarks, scorers, CLI |
| QitOS agents | `pip install snowl[qitos]` | `quick_eval_qitos()`, QitOS adapter |
| LangGraph agents | `pip install snowl[langgraph]` | `quick_eval_langgraph()`, LangGraph adapter |
| OpenAI Agents SDK | `pip install snowl[openai]` | `quick_eval_openai_agents()`, OpenAI adapter |
| All frameworks | `pip install snowl[all]` | All framework adapters |
| All benchmarks | `pip install snowl-evals` | 26 benchmark adapters |
| Cyber benchmarks | `pip install snowl-evals[cyber]` | WMDP, CyberMetric, SecQA, CyBench, CyberGym |
| Safety benchmarks | `pip install snowl-evals[safety]` | StrongReject, XSTest, AgentHarm, CoConot, FORTRESS, MASK, SevenLLM |
| Coding benchmarks | `pip install snowl-evals[coding]` | HumanEval, SWE-Bench, TerminalBench, OSWorld |

## Core Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| `httpx` | HTTP client for model providers | Yes |
| `pyyaml` | `project.yml` config loading | Yes |
| `rich` | Console output rendering | Yes |
| `click` | CLI framework | Yes |
| `openai` | OpenAI-compatible model client | Yes |

Framework adapters have their own optional dependencies (installed via extras).

## Versioning

Snowl follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking public API changes (e.g., removing `quick_eval()`, changing `Score` contract)
- **MINOR**: New features (e.g., new scorer, new benchmark adapter)
- **PATCH**: Bug fixes

### Deprecation Policy

- Deprecated features emit `DeprecationWarning` with the version they will be removed in
- Deprecated features are preserved for at least one minor version after the deprecation notice
- Migration paths are documented in the warning message

### Public API Stability

The public API is defined by what's re-exported from:
- `snowl/__init__.py`
- `snowl/core/` modules
- `snowl/scorer/__init__.py`

Internal modules (prefixed with `_` or not re-exported) may change without notice.

## Benchmark Migration Compatibility

Benchmarks migrated to `snowl-evals` are still importable from their original `snowl.benchmarks.<name>` paths with a `DeprecationWarning`. These shims will be removed in `v0.3.0`. Install `snowl-evals` for the canonical versions.
