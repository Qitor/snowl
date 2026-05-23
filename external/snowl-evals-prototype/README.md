# snowl-evals

Official benchmark adapter collection for the [Snowl](https://github.com/Qitor/snowl) agent evaluation framework.

This is the planned official benchmark collection for snowl. It depends on snowl
core, registers benchmarks through Python entry points, and contains benchmark
adapters, manifests, tests, and examples. Heavy environment benchmarks (AgentDojo,
TerminalBench, OSWorld, ToolEmu, ExploitBench) are not migrated yet.

## Installation

```bash
# Install snowl core first
pip install -e /path/to/snowl

# Install snowl-evals (editable)
pip install -e /path/to/snowl/external/snowl-evals-prototype

# Or with specific benchmark extras:
pip install -e ".[strongreject,xstest]"

# Verify
snowl bench list
snowl bench doctor
```

## Included Benchmarks

| Benchmark | Focus | Entry Point |
|-----------|-------|-------------|
| StrongReject | Refusal and safety behavior | `snowl_evals.strongreject:register` |
| XSTest | Over-refusal and unsafe-compliance | `snowl_evals.xstest:register` |
| WMDP | Cyber/chem/bio risk MCQ | `snowl_evals.wmdp:register_cyber`, `register_chem` |
| SecQA | Cybersecurity MCQ | `snowl_evals.sec_qa:register_v1`, `register_v2` |
| CyberMetric | Cybersecurity MCQ | `snowl_evals.cybermetric:register_80/500/2000/10000` |
| Coconot | Context compliance | `snowl_evals.coconot:register` |
| MASK | Misalignment assessment | `snowl_evals.mask:register` |
| SevenLLM | Chinese/English safety MCQ | `snowl_evals.sevenllm:register_mcq_en`, `register_mcq_zh` |
| Fortress | Adversarial/benign security | `snowl_evals.fortress:register_adversarial`, `register_benign` |
| AgentHarm | Agent harmfulness | `snowl_evals.agentharm:register_harm`, `register_benign` |
| AgentBench-OS | OS-level agent tasks | `snowl_evals.agent_bench_os:register` |
| BFCL | Function calling | `snowl_evals.bfcl:register` |
| IPI-Coding-Agent | Coding agent evaluation | `snowl_evals.ipi_coding_agent:register` |

## How It Works

When installed, `snowl-evals` registers benchmark adapters through Python
entry points in the `snowl.benchmarks` group. Snowl's plugin discovery
automatically finds and loads them:

```bash
snowl bench list        # Shows canonical benchmarks
snowl bench list --all  # Includes shadowed plugin entries
snowl bench doctor      # Diagnoses duplicates, manifests, and fallbacks
```

When a plugin entry point registers a name that already exists as a built-in,
the built-in takes precedence (canonical) and the plugin entry is recorded as
shadowed. This ensures a smooth transition without breaking existing workflows.

## Adding a New Benchmark

See [docs/adding_eval.md](docs/adding_eval.md).

## Extraction

This prototype lives inside the snowl repository at
`external/snowl-evals-prototype/`. Once the migration is validated, it will be
extracted into a standalone `Qitor/snowl-evals` repository. See
[docs/repository_boundaries.md](docs/repository_boundaries.md) for details.

## Status

- All phase_2_simple (lightweight) benchmarks are migrated
- Compatibility shims in `snowl/benchmarks/` emit `DeprecationWarning`
- Built-in adapters remain as fallback until deprecation period ends
- Heavy/runtime benchmarks (AgentDojo, TerminalBench, OSWorld, ToolEmu, ExploitBench) are not yet migrated
