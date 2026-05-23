# snowl-evals

Official benchmark adapter collection for the [Snowl](https://github.com/Qitor/snowl) agent evaluation framework.

This is a **local prototype** — not yet published on PyPI. It demonstrates how
third-party benchmark adapters can be packaged, registered, and discovered via
Python entry points.

## Installation

```bash
pip install -e .
# Or with specific benchmark extras:
pip install -e ".[strongreject,xstest]"
```

Requires `snowl` to be installed (editable install from the main repository).

## Included Benchmarks

| Benchmark | Focus | Entry Point |
|-----------|-------|-------------|
| StrongReject | Refusal and safety behavior | `snowl_evals.strongreject:register` |
| XSTest | Over-refusal and unsafe-compliance | `snowl_evals.xstest:register` |
| WMDP | Cyber/chem/bio risk MCQ | `snowl_evals.wmdp:register_cyber`, `register_chem` |
| SecQA | Cybersecurity MCQ | `snowl_evals.sec_qa:register_v1`, `register_v2` |
| CyberMetric | Cybersecurity MCQ | `snowl_evals.cybermetric:register_80/500/2000/10000` |

## How It Works

When installed, `snowl-evals` registers benchmark adapters through Python
entry points in the `snowl.benchmarks` group. Snowl's plugin discovery
automatically finds and loads them:

```bash
pip install -e .
snowl bench list  # Shows built-in + plugin benchmarks
```

## Adding a New Benchmark

See [docs/adding_eval.md](docs/adding_eval.md).

## Status

This is a migration prototype. The adapter code is temporarily duplicated from
the main `snowl` repository. Once the migration is complete, the originals in
`snowl/benchmarks/` will be replaced with compatibility shims and eventually
removed.
