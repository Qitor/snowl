# Round 4: Extraction Progress

Date: 2026-05-23

## Baseline Status

- snowl focused tests: 64 passed, 1 skipped
- snowl-evals prototype tests: 26 passed
- snowl full tests: 698 passed, 9 skipped (4 flaky container tests pass in isolation)
- No migration-related failures

## Extraction Path

- Source: `external/snowl-evals-prototype/`
- Target: `../snowl-evals/` (sibling directory)

## snowl-evals Package Status

- Not yet extracted
- Target version: 0.1.0.dev0
- Target structure: standalone Python package with git repo

## Cross-repo Integration Status

- Not yet tested
- Script to add: `scripts/check_snowl_evals_integration.sh`

## snowl Cleanup Status

- `external/snowl-evals-prototype/` still present
- To be replaced with `external/README.md`

## Tests Run

- Baseline: focused 64 passed, prototype 26 passed

## Blockers

- None
