# Changelog

This project keeps a human-curated changelog so users and contributors can see how Snowl evolves over time.

Format:
- `Added`: new features and capabilities
- `Changed`: behavior changes, refactors, and structural improvements
- `Fixed`: bug fixes
- `Deprecated`: old paths or APIs that will be removed later
- `Removed`: deleted features
- `Breaking`: upgrade notes for incompatible changes

## Unreleased

### Added

- Plugin discovery for `BenchmarkRegistry` — benchmarks from `snowl-evals` are now automatically discovered via `importlib.metadata.entry_points(group="snowl.benchmarks")`.
- Re-exported `JudgeClientFactory` from `snowl.scorer` public API.
- Solver pipelines, framework adapters, and bridges subpackages.
- New benchmark adapters: cybench, cybergym, gaia, humaneval, math, swe_bench, tau_bench, webarena.
- CI workflows for model evaluation and PyPI publishing.
- CONTRIBUTING.md with development workflow and PR checklist.

### Changed

- Tightened architecture boundary tests for core layer isolation.
