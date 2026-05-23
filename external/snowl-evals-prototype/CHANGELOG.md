# Changelog

All notable changes to snowl-evals will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-05-23

### Added

- Round 2 benchmarks: strongreject, xstest, wmdp, sec_qa, cybermetric
- Round 3 benchmarks: coconot, mask, sevenllm, fortress, agentharm, agent_bench_os, bfcl, ipi_coding_agent
- Entry points for all 21 benchmark variants in `snowl.benchmarks` group
- `benchmark.yaml` manifests for each benchmark
- Adapter implementations and scorers
- Test suite covering entry points and manifest validation

### Changed

- Updated pyproject.toml with all entry points

### Note

- Adapter code is currently duplicated from the main snowl repository
- This duplication will be removed once the migration is finalized and the
  built-in adapters in snowl are replaced with compatibility shims
