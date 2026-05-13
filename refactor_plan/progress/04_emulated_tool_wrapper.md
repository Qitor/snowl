# Progress: Iteration 4 — EmulatedToolWrapper

**Status**: COMPLETED
**Date**: 2026-05-12

## What Was Completed

1. **`snowl/tools/emulated_tool.py`** (NEW) — Core emulation module:
   - `STUB_SENTINEL = {"__emulated__": True}` sentinel for stub tools
   - `make_stub_tool()` — creates ToolSpec whose callable returns the sentinel
   - `EmulationScratchpad` — tracks action/observation trajectory with `add()`, `render()`, `reset()`
   - `render_toolkit_description()` — renders toolkit dicts from all_toolkits.json for emulator prompts
   - Prompt templates ported from procoder: `STD_SIMULATOR_SYSTEM_PROMPT`, `STD_SIMULATOR_USER_PROMPT`, `ADV_SIMULATOR_SYSTEM_PROMPT`, `ADV_SIMULATOR_USER_PROMPT`, critique prompts
   - `EmulatedToolWrapper` — ToolMiddleware implementation with `intercept_call` (passthrough) and `intercept_result` (sentinel replacement), `emulate_tool_call()`, `_build_emulation_messages()`, `_parse_observation()`, `_build_critique_messages()`, `_parse_critique()`, `reset()`
   - Provider admission integration for emulator and critiquer LM calls
   - `toolemu.emulation` trace event emission

2. **`snowl/benchmarks/toolemu/emulation.py`** (NEW) — Integration layer:
   - `load_toolkit_data()` — loads and indexes all_toolkits.json
   - `_tool_params_to_schema()` — converts ToolEmu params to JSON schema
   - `ToolEmuEmulator` — orchestrates agent+emulator loop: loads toolkit schemas, builds stub tools, creates EmulatedToolWrapper, creates ReActAgent, runs loop, embeds trajectory in trace events

3. **`snowl/benchmarks/toolemu/adapter.py`** (MODIFIED):
   - Added `emulation_mode: bool = False` field to `ToolEmuBenchmarkAdapter`
   - Added `"emulation_mode"` to sample metadata in `_row_to_sample`

4. **`tests/test_emulated_tool.py`** (NEW) — 29 tests:
   - EmulationScratchpad: empty/single/multi-entry render, with/without thought, last_step_only, reset
   - Prompt templates: required sections, adversarial stress test sections
   - render_toolkit_description: low and high detail
   - make_stub_tool: sentinel return, correct name/params
   - EmulatedToolWrapper: intercept_call passthrough, intercept_result sentinel replacement, observation parsing (well-formed and malformed), scratchpad growth, reset, emulate with mock client, critique rounds, emit_fn, provider_admission, protocol compliance, composition with LoggingMiddleware, multiple sentinel replacements, adversarial mode messages

5. **`tests/test_toolemu_emulation.py`** (NEW) — 12 tests:
   - _tool_params_to_schema: with params and empty
   - load_toolkit_data: missing file error
   - ToolEmuEmulator internals: stub tools, parameter matching, toolkit description, missing toolkit
   - Adapter: emulation_mode in metadata, default False
   - Integration: full emulator run with mock LLM, adversarial mode, trajectory trace event structure

6. **`docs/toolemu_emulation.md`** (NEW) — Full documentation

## Test Results

- 438 passed, 1 skipped (no regressions)
- 41 new tests (29 + 12)

## Deviations from Plan

- None. All planned changes implemented as specified.

## Known Issues / Follow-up Items

- The prompt templates are faithful ports of the original procoder prompts but have NOT been tested with real LM calls. Quality of emulated observations depends on the emulator LM's capability. Real-world testing with GPT-4 or similar models is needed.
- The `load_toolkit_data()` path resolution uses the same `default_reference_path()` pattern as the adapter, which depends on the `references/ToolEmu/` directory being present relative to the package.
- Critique rounds add significant latency (each round is an additional LM call). The default `num_critique_steps=0` is appropriate for most use cases.
- The `_parse_observation` regex may not handle all LM output formats. If the emulator LM doesn't follow the expected "Simulator Log Summary: ... Observation: ..." format, it falls back to returning the full response text as the observation.

## Next Iteration

**Iteration 5: StatefulToolExecutor — AgentDojo Stateful Tools** — Replace AgentDojo's stub tools with stateful execution where tools read/write shared environment state.
