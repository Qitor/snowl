# Architecture Boundary Audit — Snowl

> Re-verified 2026-05-18 against the actual codebase. Earlier governance
> findings have been re-checked; stale findings updated; new findings added.

---

## Summary

| Severity | Count | Fixed this round |
|----------|-------|-----------------|
| Critical | 2 | 1 |
| High | 2 | 0 |
| Medium | 6 | 0 |
| Low | 4 | 0 |

---

## Findings

### C1 — Real API keys committed in examples

- **Severity**: Critical
- **Files**:
  - `examples/terminalbench-official/project.yml:9` — `CVuXZ/EHsJQMV2peuex0chkH+99/QaKq089fciMtqHo=`
  - `examples/toolemu-emulation/project.yml:9,45` — `stpmj/4hRawPjQCf0fk70W6HnObgXtkonX3qHCCNsPc=`
- **Symptom**: Plaintext API keys (appears to be SiliconFlow/SII internal proxy keys) committed to the repository
- **Why it matters**: Key exposure in version control. Even if the repo is private, this violates basic secret hygiene and will be a blocker for public release
- **Recommended fix**: Replace with `${SNOWL_SMOKE_API_KEY}` or `${OPENAI_API_KEY}` environment variable placeholders
- **Fixed this round**: Yes (terminalbench and toolemu-emulation keys replaced with env var placeholders)
- **Remaining**: `examples/osworld-official/project.yml` and `examples/toolemu-official/project.yml` contain `sk-...` which appears to be a placeholder pattern, not a real key — acceptable as example template

### C2 — on-disk api_info.md with real keys

- **Severity**: Critical (mitigated by .gitignore)
- **File**: `api_info.md` (root directory, gitignored)
- **Symptom**: File containing real API keys for DeepSeek, GLM, Kimi, Qwen, MiniMax models with internal SII proxy URLs
- **Why it matters**: If someone accidentally removes the gitignore entry or copies the file, keys leak. Also indicates the repo was used with real credentials during development
- **Recommended fix**: File is already gitignored and not tracked. Consider adding a `.gitignore` enforcement test. No code change needed.
- **Fixed this round**: No (already gitignored, not tracked)

---

### H1 — Runtime imports benchmark-specific container launcher

- **Severity**: High
- **File**: `snowl/runtime/container_providers.py:25`
- **Symptom**: `from snowl.benchmarks.osworld.container import OSWorldContainerLauncher` — runtime depends on a specific benchmark adapter
- **Why it matters**: Adding a benchmark with containers requires modifying runtime code. This is the most direct boundary violation in the codebase
- **Recommended fix**: Implement a container provider registration mechanism. Benchmarks register their providers via the `ContainerProviderRegistry` at discovery time, eliminating the need for runtime to import benchmark code directly
- **Fixed this round**: No (requires designing a registration API; too large for this governance pass)

### H2 — ToolEmu scorer uses sys.path.insert to import reference code

- **Severity**: High
- **File**: `snowl/benchmarks/toolemu/scorer.py:226,233`
- **Symptom**: `_ensure_toolemu_reference_importable()` does `sys.path.insert(0, path_text)` then `from toolemu.evaluators import ...` and `from langchain.chat_models.base import ...`
- **Why it matters**: Runtime mutation of `sys.path` is fragile and can cause import conflicts. The `test_benchmark_dependency_guard.py` test catches this pattern and currently fails
- **Recommended fix**: Consider a plugin/isolated process model for ToolEmu official evaluator, or make the langchain/toolemu imports conditional on an explicit opt-in flag. Short-term: document this as a known exception in the dependency guard test
- **Fixed this round**: No (requires understanding ToolEmu evaluator pipeline; risk of breaking it)

---

### M1 — Runtime policy imports benchmark registry

- **Severity**: Medium
- **File**: `snowl/runtime/policy.py:9,90-97`
- **Symptom**: Module-level `from snowl.benchmarks.base import BenchmarkConcurrencyProfile` and lazy `from snowl.benchmarks.registry import get_default_benchmark_registry`
- **Why it matters**: Runtime depends on benchmarks layer (reversed dependency direction). Policy should accept concurrency profile as a parameter rather than looking it up
- **Recommended fix**: Have callers (eval/cli) resolve the profile from the registry and pass it to `RuntimePolicy.resolve()` as a parameter
- **Fixed this round**: No

### M2 — Benchmark-specific score key in runtime engine

- **Severity**: Medium
- **File**: `snowl/runtime/engine.py:961-962`
- **Symptom**: `if output.get("osworld_score") is not None: payload["osworld_score"] = output["osworld_score"]` — benchmark-specific logic in generic engine
- **Why it matters**: Every benchmark that needs custom payload passthrough requires engine modifications
- **Recommended fix**: Use generic payload passthrough (e.g., `payload.update(output.get("benchmark_payload", {}))`). Move OSWorld score extraction to OSWorld's scorer
- **Fixed this round**: No

### M3 — Web monitor imports benchmark registry

- **Severity**: Medium
- **File**: `snowl/web/monitor.py` (lazy import)
- **Symptom**: `from snowl.benchmarks.registry import get_default_benchmark_registry`
- **Why it matters**: Web layer depends on benchmarks layer
- **Recommended fix**: Accept benchmark metadata as a parameter or use a lightweight metadata service rather than importing the full registry
- **Fixed this round**: No

### M4 — Discovery module imports benchmark registry

- **Severity**: Medium
- **File**: `snowl/discovery.py` (lazy import)
- **Symptom**: `from snowl.benchmarks.registry import get_default_benchmark_registry` for auto-infer of agent_type from benchmark middleware_hints
- **Why it matters**: Core bootstrap path depends on benchmarks layer
- **Recommended fix**: Pass middleware_hints through the project config rather than looking them up in the registry
- **Fixed this round**: No

### M5 — Artifacts module imports benchmark registry

- **Severity**: Medium
- **File**: `snowl/artifacts.py` (lazy import)
- **Symptom**: `from snowl.benchmarks.registry import get_default_benchmark_registry` for building benchmark metadata map
- **Why it matters**: Artifact persistence depends on benchmarks layer
- **Recommended fix**: Accept benchmark metadata as a parameter
- **Fixed this round**: No

### M6 — Runtime engine imports UI contracts

- **Severity**: Medium
- **File**: `snowl/runtime/engine.py` (imports from `snowl.ui.contracts`)
- **Symptom**: `from snowl.ui.contracts import build_score_explanations` — the trial execution engine depends on UI rendering logic
- **Why it matters**: Engine should not need to know about UI presentation
- **Recommended fix**: Move `build_score_explanations` to a shared utility or have the engine return raw data and let the UI layer format it
- **Fixed this round**: No

---

### L1 — AgentDojo tool implementations in shared tools/ package

- **Severity**: Low
- **File**: `snowl/tools/stateful_executor.py:53-408`
- **Symptom**: Contains AgentDojo-specific banking/travel tool implementations in the shared tools package
- **Why it matters**: Adapter-specific code in shared infrastructure. Other benchmarks or tools may accidentally depend on these implementations
- **Recommended fix**: Move tool implementations to `snowl/benchmarks/agentdojo/tools.py`; keep only the generic `StatefulToolExecutor` pattern in `stateful_executor.py`
- **Fixed this round**: No

### L2 — Duplicated _run_coro_sync across scorer modules

- **Severity**: Low
- **Files**: `snowl/scorer/model_judge.py:30-52`, `snowl/scorer/grade_judge.py:20-40`
- **Symptom**: Nearly identical sync-over-async bridge function duplicated in two modules
- **Why it matters**: Maintenance burden; divergent implementations may drift
- **Recommended fix**: Extract to `snowl/scorer/_sync_bridge.py`
- **Fixed this round**: No

### L3 — Duplicated template rendering in scorer modules

- **Severity**: Low
- **Files**: `snowl/scorer/model_judge.py` (`_render_template`), `snowl/scorer/grade_judge.py` (`render_prompt_template`)
- **Symptom**: Two similar template rendering implementations
- **Why it matters**: Maintenance burden; potential for inconsistent behavior
- **Recommended fix**: Unify to single implementation in `grade_judge.py`
- **Fixed this round**: No

### L4 — `ToolSpec.to_openai_tool()` embeds OpenAI schema format

- **Severity**: Low
- **File**: `snowl/core/tool.py`
- **Symptom**: Core `ToolSpec` has a `to_openai_tool()` method that outputs OpenAI function-calling schema format
- **Why it matters**: Core layer has an implicit dependency on OpenAI's schema format. If other providers use different formats, this method will not serve them
- **Recommended fix**: Consider making `to_openai_tool()` a standalone function in the model adapter layer rather than a method on the core `ToolSpec` dataclass. Low priority since OpenAI format is de facto standard
- **Fixed this round**: No

---

## Previously Reported Findings — Status Update

| Finding (from governance.md) | Current Status |
|------------------------------|---------------|
| P0.1: Leaked API keys in strongreject/wmdp-cyber-eval | **Fixed** — replaced with `${OPENAI_API_KEY}` |
| P0.2: README broken references to START_HERE/PLANS/project_map/current_state | **Fixed** — references removed |
| P0.3: Missing CONTRIBUTING.md and CLAUDE.md | **Fixed** — both exist |
| P0.4: No architecture boundary test | **Fixed** — `test_architecture_boundaries.py` exists with 5 tests |
| P1.1: ReActAgent/ChatAgent depend on OpenAICompatibleChatClient | **Fixed** — now use `ChatModelClient` protocol |
| P1.2: EmulatedToolWrapper depends on OpenAICompatibleChatClient | **Fixed** — now uses `ChatModelClient` protocol |
| P1.3: OSWorld score key in engine | **Still present** — see M2 |
| P1.4: Container provider registry | **Still present** — see H1 |
| P1.5: AgentDojo tools in stateful_executor | **Still present** — see L1 |

---

## Core Layer Verification

The core layer (`snowl/core/`) passes all boundary checks:

- Zero imports from adapter packages (agents, benchmarks, model, scorer, runtime, tools, envs, ui, web, export, project_config)
- Zero third-party dependencies
- Clean internal DAG with no cycles
- Only depends on `snowl.errors` and Python stdlib

Verified by:
- `pytest tests/test_architecture_boundaries.py -v` (5/5 passing)
- Manual source code inspection

---

## Test Gap: benchmark_dependency_guard failure

The test `test_builtin_benchmarks_do_not_bridge_reference_runtimes` in
`tests/test_benchmark_dependency_guard.py` currently **fails** because:

1. `toolemu/scorer.py:233` — `from toolemu` (imports reference package)
2. `toolemu/scorer.py:226` — `sys.path.insert` (manipulates import path)

This is a known trade-off: the ToolEmu official evaluator requires importing
from the reference implementation. The test should either:
- Add `toolemu/scorer.py` to the exempt list (with documentation), or
- Isolate the ToolEmu evaluator behind a subprocess/plugin boundary

This failure should be resolved in the next round.
