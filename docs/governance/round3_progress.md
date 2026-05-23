# Round 3 Progress

Date: 2026-05-23

## Baseline Status

- snowl tests: 670 passed, 0 failed, 9 skipped
- snowl-evals prototype tests: 18 passed (Round 2 baseline)
- Dependency guard: PASSING
- All 21 benchmark families have manifests

## Migration Status

### Migrated (Round 2)
- strongreject, xstest, wmdp, sec_qa, cybermetric

### Migrated (Round 3)
- coconot, mask, sevenllm, fortress, agentharm, agent_bench_os, bfcl, ipi_coding_agent

### Do NOT migrate (phase_3_heavy)
- agentdojo, agentsafetybench, terminalbench, osworld, toolemu, exploitbench

### Keep in core
- jsonl, csv (generic adapters)

## Shim Status

All 13 migrated benchmarks have deprecation warnings in their `__init__.py`:
- strongreject, xstest, wmdp, sec_qa, cybermetric
- coconot, mask, sevenllm, fortress, agentharm, agent_bench_os, bfcl, ipi_coding_agent

No deferred shims. All shims tested in `tests/test_benchmark_compat_shims.py` (32 tests).

## Duplicate Handling

- Built-in entries win over plugin duplicates (canonical)
- Plugin duplicates stored in `_shadowed` dict (not silently discarded)
- Warning emitted when plugin duplicates are shadowed
- `snowl bench list --all` shows shadowed entries
- `snowl bench doctor` reports shadowed entries and migrated benchmarks using built-in fallback
- Tests: `tests/test_benchmark_registry_duplicates.py` (8 tests)

## Source Precedence Policy

1. Built-in registration is canonical during transition
2. Plugin entries with duplicate names are shadowed (stored, not discarded)
3. `registry.create()` always uses canonical (built-in) entry
4. Plugin-plugin duplicates: second overwrites first, no shadowing
5. Empty benchmark names raise `SnowlValidationError`

## Test Results

### Duplicate handling tests
```
8 passed
```

### Compat shim tests
```
32 passed
```

### Full snowl suite
```
670 passed, 9 skipped
```

## snowl-evals Prototype Status

- All 13 phase_2_simple benchmarks have adapter packages in `snowl_evals/`
- All 21 entry point variants in pyproject.toml
- Tests: `tests/test_entrypoints.py` (entry point registration)
- CI skeleton: `.github/workflows/ci.yml`
- Docs: `docs/adding_eval.md`, `docs/release_checklist.md`, `docs/repository_boundaries.md`
- Files: README.md, CHANGELOG.md, LICENSE

## Remaining Blockers

- None. All phase_2_simple benchmarks are migrated and tested.
- Phase_3_heavy benchmarks deferred until container provider interface stabilizes.
