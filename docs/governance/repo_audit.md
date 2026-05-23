# Repository Audit — snowl

Date: 2026-05-23

## Classification

### Core Framework (stays in `snowl`)

| Module | Location | Migration Risk | Notes |
|--------|----------|---------------|-------|
| Core contracts | `snowl/core/` | None | Foundational protocols — must stay |
| Errors | `snowl/errors.py` | None | Shared exception class |
| Model client | `snowl/model/` | None | ChatModelClient protocol + OpenAI impl |
| Agents | `snowl/agents/` | None | ChatAgent, ReActAgent |
| Agent adapters | `snowl/adapters/` | None | LangGraph, OpenAI SDK wrappers |
| Tools & middleware | `snowl/tools/` | None | ToolSpec, MiddlewareChain, StatefulToolExecutor |
| Environments | `snowl/envs/` | None | Terminal, GUI, sandbox backends |
| Scorers (generic) | `snowl/scorer/` | Low | Built-in scorer strategies — stay |
| Runtime engine | `snowl/runtime/` | None | Trial execution, container lifecycle |
| Project config | `snowl/project_config.py` | None | project.yml loader |
| Eval orchestration | `snowl/eval.py`, `discovery.py`, `dispatch.py`, `eval_loop.py`, `eval_spec.py`, `planning.py`, `retry.py`, `rescore.py` | None | Core eval pipeline |
| Bench/suite bridge | `snowl/bench.py`, `suite.py` | None | Benchmark → eval adapter |
| CLI | `snowl/cli.py` | None | Top-level entry point |
| Aggregation | `snowl/aggregator/` | None | Schema + metrics + summary |
| Observability | `snowl/observability/` | None | Event bus |
| Reporting | `snowl/report/` | None | HTML reports |
| UI | `snowl/ui/` | None | Terminal UI |
| Web monitor | `snowl/web/` | None | Web runtime + store |
| Export | `snowl/export/` | None | OpenAI trace export |
| Utils | `snowl/utils/` | None | Env helpers |
| Examples lint | `snowl/examples_lint.py` | None | Static checks |
| Artifacts | `snowl/artifacts.py` | None | Run artifact persistence |

### Generic Reference Adapters (stays in `snowl`)

| Module | Location | Migration Risk | Notes |
|--------|----------|---------------|-------|
| Benchmark base/registry | `snowl/benchmarks/base.py`, `base_adapter.py`, `registry.py` | None | Must stay — core adapter contracts |
| CSV adapter | `snowl/benchmarks/csv_adapter.py` | None | Generic data adapter |
| JSONL adapter | `snowl/benchmarks/jsonl_adapter.py` | None | Generic data adapter |
| External adapter | `snowl/benchmarks/external.py` | None | Plugin loading |
| Conformance | `snowl/benchmarks/conformance.py` | None | Adapter validation |
| Assets | `snowl/benchmarks/assets.py` | None | Download/cache helpers |
| Example task | `snowl/benchmarks/example_task.py` | None | Minimal fixture |
| Benchmark utils | `snowl/benchmarks/utils/` | None | Shared I/O, filtering, splitting |
| Manifest | `snowl/benchmarks/manifest.py` | None | Benchmark manifest schema (new) |

### Built-in Benchmark Adapters (migrate to `snowl-evals`)

| Benchmark | Location | .py files | Heavy deps? | Container? | Migration Phase |
|-----------|----------|-----------|-------------|------------|-----------------|
| AgentDojo | `snowl/benchmarks/agentdojo/` | 6 | No | No | Phase 2 |
| ToolEmu | `snowl/benchmarks/toolemu/` | 5 | Yes (emulation) | No | Phase 3 |
| AgentSafetyBench | `snowl/benchmarks/agentsafetybench/` | 7 | Yes (executor) | Yes | Phase 3 |
| TerminalBench | `snowl/benchmarks/terminalbench/` | 4 | No | Yes (docker) | Phase 3 |
| OSWorld | `snowl/benchmarks/osworld/` | 6 | Yes (many) | Yes (docker+GUI) | Phase 3 |
| ExploitBench | `snowl/benchmarks/exploitbench/` | 7 | Yes (mcp SDK) | Yes (docker+MCP) | Phase 3 |
| StrongReject | `snowl/benchmarks/strongreject/` | 3 | No (judge) | No | Phase 2 |
| WMDP | `snowl/benchmarks/wmdp/` | 2 | No (HF) | No | Phase 2 |
| BFCL | `snowl/benchmarks/bfcl/` | 3 | No | No | Phase 2 |
| XSTest | `snowl/benchmarks/xstest/` | 3 | No (judge) | No | Phase 2 |
| AgentHarm | `snowl/benchmarks/agentharm/` | 3 | No (judge) | No | Phase 2 |
| MASK | `snowl/benchmarks/mask/` | 2 | No | No | Phase 2 |
| SecQA | `snowl/benchmarks/sec_qa/` | 2 | No | No | Phase 2 |
| SevenLLM | `snowl/benchmarks/sevenllm/` | 2 | No (HF) | No | Phase 2 |
| CyberMetric | `snowl/benchmarks/cybermetric/` | 2 | No | No | Phase 2 |
| CoConot | `snowl/benchmarks/coconot/` | 3 | No (judge) | No | Phase 2 |
| Fortress | `snowl/benchmarks/fortress/` | 3 | No (judge) | No | Phase 2 |
| IPI Coding Agent | `snowl/benchmarks/ipi_coding_agent/` | 3 | No | No | Phase 2 |
| AgentBench-OS | `snowl/benchmarks/agent_bench_os/` | 3 | No | No | Phase 2 |

### Examples (stays in `snowl` for now, migrate to `snowl-recipes` later)

| Example | Location | Migration Risk |
|---------|----------|---------------|
| agent-safety-sweep | `examples/agent-safety-sweep/` | Low |
| agentdojo | `examples/agentdojo/` | Low (depends on benchmark) |
| agents/* | `examples/agents/` | Low (generic patterns) |
| agentsafetybench-official | `examples/agentsafetybench-official/` | Low |
| agentsafetybench | `examples/agentsafetybench/` | Low |
| e2e-capability | `examples/e2e-capability/` | Low |
| e2e-safety | `examples/e2e-safety/` | Low |
| e2e-tooluse | `examples/e2e-tooluse/` | Low |
| osworld-official | `examples/osworld-official/` | Low |
| plugins/snowl-bench-example | `examples/plugins/snowl-bench-example/` | Low (plugin template) |
| safety-benchmark-smoke | `examples/safety-benchmark-smoke/` | Low |
| sandbox-coding-smoke | `examples/sandbox-coding-smoke/` | Low |
| strongreject-official | `examples/strongreject-official/` | Low |
| terminalbench-official | `examples/terminalbench-official/` | Low |
| toolemu-emulation | `examples/toolemu-emulation/` | Low |
| toolemu-official | `examples/toolemu-official/` | Low |
| wmdp-chem-official | `examples/wmdp-chem-official/` | Low |
| wmdp-cyber-eval | `examples/wmdp-cyber-eval/` | Low |
| wmdp-cyber-official | `examples/wmdp-cyber-official/` | Low |

### Web Monitor (stays in `snowl`)

| Module | Location | Notes |
|--------|----------|-------|
| Web UI (Next.js) | `webui/` | Independent app, communicates via API |
| Web runtime | `snowl/web/` | Process lifecycle management |

### Tests (stays in `snowl`)

| Category | Location | Notes |
|----------|----------|-------|
| Core fast tests | `tests/test_core_*.py`, `tests/test_architecture_boundaries.py` | Must stay |
| Adapter conformance | `tests/test_benchmark_*.py` | Migrate benchmark-specific ones with adapters |
| Integration tests | `tests/e2e/` | Stay |
| Agent tests | `tests/test_agent_*.py` | Stay |

## Migration Priority Matrix

| Phase | Action | Benchmarks | Risk |
|-------|--------|------------|------|
| Phase 1 | Establish contracts, keep all built-in | None | None |
| Phase 2 | Migrate simple row-oriented benchmarks | StrongReject, WMDP, BFCL, XSTest, MASK, SecQA, SevenLLM, CyberMetric, CoConot, Fortress, IPI, AgentBench-OS, AgentHarm | Low — no containers, simple adapters |
| Phase 3 | Migrate heavy environment benchmarks | AgentDojo, ToolEmu, AgentSafetyBench, TerminalBench, OSWorld, ExploitBench | Medium — containers, providers, custom agents |
| Phase 4 | Remove deprecated adapters from core | All migrated | Low — with compatibility shims |

## Manifest Status

All built-in benchmarks have manifests. All phase_2_simple benchmarks also have manifests in the `snowl-evals` prototype.

| Benchmark | Manifest in snowl | Manifest in snowl-evals | Deprecated? |
|-----------|------------------|------------------------|-------------|
| jsonl | Done | N/A (keep in core) | No |
| strongreject | Done | Done | Yes |
| xstest | Done | Done | Yes |
| wmdp | Done | Done | Yes |
| sec_qa | Done | Done | Yes |
| cybermetric | Done | Done | Yes |
| coconot | Done | Done | Yes |
| mask | Done | Done | Yes |
| sevenllm | Done | Done | Yes |
| fortress | Done | Done | Yes |
| agentharm | Done | Done | Yes |
| agent_bench_os | Done | Done | Yes |
| bfcl | Done | Done | Yes |
| ipi_coding_agent | Done | Done | Yes |
| agentdojo | Done | N/A (phase_3_heavy) | No |
| agentsafetybench | Done | N/A (phase_3_heavy) | No |
| terminalbench | Done | N/A (phase_3_heavy) | No |
| osworld | Done | N/A (phase_3_heavy) | No |
| toolemu | Done | N/A (phase_3_heavy) | No |
| exploitbench | Done | N/A (phase_3_heavy) | No |
