# Round 4: Extraction Progress

Date: 2026-05-23

## Baseline Status

- snowl focused tests: 64 passed, 1 skipped
- snowl full tests: 698 passed, 9 skipped (4 flaky container tests pass in isolation)
- snowl-evals prototype tests: 26 passed
- No migration-related failures

## Extraction Path

- Source: `external/snowl-evals-prototype/` (removed)
- Target: `../snowl-evals/` (standalone sibling directory)
- GitHub: https://github.com/Qitor/snowl-evals

## snowl-evals Package Status

- Location: `/Users/morinop/snowl-evals/` (local) + `Qitor/snowl-evals` (GitHub)
- Version: 0.1.0.dev0
- Git initialized: Yes
- Committed: Yes (commit 542ea9b)
- Pushed: Yes (to https://github.com/Qitor/snowl-evals)
- 104 tests passing (26 entrypoints + 5 manifest + 73 adapter conformance)

## Cross-repo Integration Status

- `pip install -e . && pip install -e ../snowl-evals` works
- `snowl bench list` shows 29 canonical benchmarks
- `snowl bench list --all` shows 21 additional shadowed plugin entries
- `snowl bench doctor` passes all 6 checks
- `scripts/check_snowl_evals_integration.sh` passes

## snowl Cleanup Status

- `external/snowl-evals-prototype/` removed (git rm)
- `external/README.md` added pointing to sibling snowl-evals
- Docs updated: README.md, CONTRIBUTING.md, plugin_contract.md, migration_to_snowl_evals.md
- Deprecation policy: `docs/governance/deprecation_policy.md`

## Tests Run

| Suite | Result |
|-------|--------|
| snowl focused | 64 passed, 1 skipped |
| snowl full | 698 passed, 9 skipped |
| snowl-evals | 104 passed |
| cross-repo integration script | PASSED |

## Blockers

- None. Extraction complete.
