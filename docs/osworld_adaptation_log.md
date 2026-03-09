# OSWorld Adaptation Log

## 2026-03-04

### Scope
- Unified adaptation PR for `osworld` integration and debugging.
- Keep framework-level fixes in `snowl/` and example ergonomics in `examples/osworld-official/`.

### Baseline Reproduction
- Command:
  - `python -m snowl.cli bench run osworld --project examples/osworld-official --split test --limit 1 --max-trials 1 --no-ui`
- Result:
  - `error=1/1`, error code `container_runtime_error`.
- Root cause:
  - Host missing `docker` executable in `PATH` (`WinError 2` from `docker run`).

### Changes In Progress
- Added Docker preflight in container runtime:
  - fail early with explicit `docker_not_found` error and actionable message.
  - include `docker_path` in container config runtime events when available.
- Added sample limit control for example task:
  - `SNOWL_OSWORLD_SAMPLE_LIMIT` (default `20`, supports `1` for smoke run).
- Updated `examples/osworld-official/README.md` with sample limit env var.

### Next Validation
- Re-run single-sample OSWorld command and verify clear preflight error text.
- Run targeted tests:
  - `pytest -q tests/test_osworld_benchmark.py`
  - `pytest -q tests/test_runtime_engine.py`

### Validation Result
- Re-run result:
  - preflight now emits `runtime.env.preflight.error` with `code=docker_not_found`.
  - error message is explicit and actionable (no raw `WinError 2` only).
- Example limit result:
  - `SNOWL_OSWORLD_SAMPLE_LIMIT=1` + `snowl eval examples/osworld-official` now runs exactly `total=1`.
- Tests:
  - `python -m pytest -q tests/test_osworld_benchmark.py tests/test_runtime_engine.py`
  - `11 passed`.

### 2026-03-04 (Round 2)

#### Newly Observed Failure
- Docker is available, image pulls successfully, but OSWorld container exits with:
  - `ERROR: No boot disk specified, set BOOT= to the URL of a disk image file.`
- This was confirmed from container logs for container image `happysixd/osworld-docker`.

#### Framework Fixes
- Fixed OSWorld startup exit-code bug:
  - previous logic used `int(start_evt.get("exit_code", 1) or 1)` and misclassified `0` as failure.
  - now parses exit code explicitly and correctly.
- Added readiness-failure diagnostics:
  - when `ready=false`, fetch `docker logs --tail 120`, attach logs to error, and clean up container.
  - adds explicit hint for missing boot disk (`BOOT`/qcow2 mapping).
- Added Windows-safe docker output decoding:
  - `subprocess.run(..., encoding="utf-8", errors="replace")` in `GuiEnv` start/stop/logs path.
- Updated test mock signature for `subprocess.run` kwargs compatibility.

#### Reproduction Command (Short Timeout)
- `SNOWL_OSWORLD_READY_TIMEOUT=20 python -m snowl.cli bench run osworld --project examples/osworld-official --split test --limit 1 --max-trials 1 --no-ui`

#### Current Status
- Error is now explicit in `run.log`:
  - includes the exact QEMU boot-disk message and framework-level remediation hint.

### 2026-03-04 (Round 3)

#### Boot-Disk Adaptation (Framework Layer)
- Added OSWorld boot-disk preflight before container start:
  - requires at least one of:
    - `SNOWL_OSWORLD_BOOT` (disk image URL), or
    - `SNOWL_OSWORLD_VM_PATH` (local qcow2 file path, mounted to `/System.qcow2`).
- Added optional runtime resource env mapping:
  - `SNOWL_OSWORLD_DISK_SIZE` -> `DISK_SIZE`
  - `SNOWL_OSWORLD_RAM_SIZE` -> `RAM_SIZE`
  - `SNOWL_OSWORLD_CPU_CORES` -> `CPU_CORES`
  - `SNOWL_OSWORLD_KVM` -> `KVM`
- Added container config telemetry:
  - `boot_config.boot_url_set`
  - `boot_config.vm_path_set`

#### Validation
- Without boot config:
  - now fails fast with:
    - `runtime.env.preflight.error`
    - `code=osworld_boot_not_configured`
    - actionable message for `SNOWL_OSWORLD_BOOT` / `SNOWL_OSWORLD_VM_PATH`.
- Targeted tests still pass:
  - `python -m pytest -q tests/test_osworld_benchmark.py tests/test_runtime_engine.py`
  - `11 passed`.

### 2026-03-04 (Round 4)

#### BOOT URL Runtime Check
- Ran with:
  - `SNOWL_OSWORLD_BOOT=https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip`
  - `SNOWL_OSWORLD_READY_TIMEOUT=20`
- Result:
  - no longer hits "No boot disk specified".
  - container logs show VM image download in progress (`Downloading Ubuntu.qcow2.zip...`).
  - trial fails due readiness timeout (expected with short timeout), not boot-disk misconfiguration.

#### Framework Hint Improvement
- Added timeout guidance when logs indicate qcow2 download:
  - suggests increasing `SNOWL_OSWORLD_READY_TIMEOUT` (e.g. `1800`) on first boot.

### 2026-03-04 (Round 5)

#### UX-Focused Boot Adaptation
- Removed user-facing hard requirement to manually set `SNOWL_OSWORLD_BOOT`.
- Added framework auto-prepare path for OSWorld VM disk:
  - default URL: `xlangai/ubuntu_osworld` qcow2 zip.
  - cache directory: `references/OSWorld/docker_vm_data`.
  - first-run auto download/extract; later runs reuse cached qcow2.
- Boot input resolution priority:
  1. `SNOWL_OSWORLD_VM_PATH` (explicit local qcow2)
  2. `SNOWL_OSWORLD_BOOT` (explicit URL, legacy/advanced)
  3. framework auto-cache (default, recommended)

#### Timeout Behavior
- If `SNOWL_OSWORLD_READY_TIMEOUT` is unset:
  - cached VM run uses default timeout (240s).
  - first boot/download path auto-extends timeout (1800s).
- Goal: hide timeout tuning for normal users and only require patience on first run.

#### Docs Update
- Updated `examples/osworld-official/README.md`:
  - removed BOOT/TIMEOUT env from quickstart.
  - added note that first run auto-downloads and may take long.

### 2026-03-04 (Round 6)

#### Networking Capability Fix (Framework Layer)
- Reproduced container startup stall with logs:
  - `RTNETLINK answers: Operation not permitted`
  - `ERROR: Failed to create bridge. Please add ... --cap-add NET_ADMIN`
- Added container capability support to GUI runtime:
  - `GuiEnv.start_container(..., cap_add=...)` now maps to Docker `--cap-add`.
- Added OSWorld default capability injection in container runtime:
  - new resolver `SNOWL_OSWORLD_CAP_ADD` (default `NET_ADMIN`, supports disable via `none/false/0`).
  - runtime telemetry now includes `cap_add` in `osworld.container.config`.
- Aligned example fallback agent path:
  - non-runtime-managed startup also passes parsed capability set.

#### Validation
- Confirmed current stuck run command lacked `--cap-add`.
- Confirmed running container logs explicitly require `NET_ADMIN`.
- Added/updated test assertion:
  - `tests/test_osworld_benchmark.py` now verifies docker run command includes `--cap-add NET_ADMIN` when requested.

### 2026-03-04 (Round 7)

#### Runtime Re-check After NET_ADMIN Patch
- Smoke command:
  - `SNOWL_OSWORLD_READY_TIMEOUT=25 SNOWL_OSWORLD_SAMPLE_LIMIT=1 python -m snowl.cli bench run osworld --project examples/osworld-official --split test --limit 1 --max-trials 1 --no-ui`
- New run artifact:
  - `examples/osworld-official/.snowl/runs/20260304T083501Z/run.log`
- Verified runtime command now includes:
  - `docker run -d --cap-add NET_ADMIN ...`
- Result:
  - no `Failed to create bridge` / `RTNETLINK` errors in captured logs.
  - trial still timed out at 25s readiness window (expected on Windows + QEMU cold boot), so next tuning focus is startup/readiness strategy rather than missing capability.

### 2026-03-04 (Round 8)

#### Parallel Startup Port-Collision Fix (OSWorld Layer First)
- Reproduced latest run failure:
  - `Bind for 0.0.0.0:5000 failed: port is already allocated` when `max_trials=2`.
- Root cause in Snowl OSWorld path:
  - startup used fixed host ports (`5000/9222/8006/8080`) for every trial.
  - concurrent trial startup causes deterministic collision.

#### Changes
- Added OSWorld dynamic host-port resolver in `ContainerRuntime`:
  - default behavior now auto-picks free localhost ports per trial.
  - optional explicit pinning remains available via:
    - `SNOWL_OSWORLD_SERVER_PORT`
    - `SNOWL_OSWORLD_CHROMIUM_PORT`
    - `SNOWL_OSWORLD_VNC_PORT`
    - `SNOWL_OSWORLD_VLC_PORT`
- Added startup retry for port collisions:
  - retries on `port is already allocated` when ports are auto-assigned.
  - emits `osworld.container.retry` telemetry.
- Switched qcow2 mount to read-only:
  - host vm mapping now uses `/System.qcow2:ro` for safer concurrent reads.
- Added richer container config telemetry:
  - `ports`, `ports_explicit`, `start_retries`.

#### Scope Justification
- Kept fix inside OSWorld container runtime path first (no global scheduler changes).
- Minimal shared/runtime adjustments are only:
  - generic local TCP availability checks and retry control used by OSWorld startup path.
- Reusable rationale (if promoted later):
  - any benchmark that boots long-lived dockerized services with fixed host ports has the same collision pattern under concurrent trials.

### 2026-03-04 (Round 9)

#### Validation
- Targeted tests:
  - `python -m pytest -q tests/test_osworld_container_runtime.py tests/test_osworld_benchmark.py tests/test_runtime_engine.py`
  - `13 passed`.
- CLI conformance:
  - `python -m snowl.cli bench check osworld` -> all checks pass.
- Runtime smoke with concurrent setting:
  - `SNOWL_OSWORLD_MAX_STEPS=0 SNOWL_OSWORLD_SAMPLE_LIMIT=2 python -m snowl.cli bench run osworld --project examples/osworld-official --split test --limit 2 --max-trials 2 --no-ui`
  - result: `error=0` (both samples incorrect by scorer, but no container startup error).
- Observed behavior:
  - startup command now mounts VM as read-only (`/System.qcow2:ro`).
  - no `port is already allocated` in this validation run.

### 2026-03-04 (Round 10)

#### Execution Capability Gap Fix (OSWorld Layer First)
- Aligned `GuiEnv` action mapping with OSWorld `PythonController` major action set:
  - added support for `MOVE_TO`, `MOUSE_MOVE`, `RIGHT_CLICK`, `DOUBLE_CLICK`,
    `MOUSE_DOWN`, `MOUSE_UP`, `DRAG_TO`, `KEY_DOWN`, `KEY_UP`, `HOTKEY`.
  - improved `SCROLL` parity with `dx/dy` -> `hscroll/vscroll`.
  - kept `WAIT|DONE|FAIL` special handling.
- Added direct command passthrough in `GuiEnv.execute_action` for action payloads that already provide `command/shell`.

#### Observability and Replay
- Added optional richer observation fields in `GuiEnv.observe(...)`:
  - `include_accessibility=True` -> fetch `/accessibility`.
  - `include_terminal=True` -> fetch `/terminal`.
- Added recording APIs in `GuiEnv`:
  - `start_recording()`
  - `end_recording()`
  - `save_recording(path)`
- Updated `examples/osworld-official/agent.py`:
  - expanded action schema in system prompt to include the full action subset above.
  - emits `runtime.model.io` events for full request/response visibility.
  - writes richer `trace_events` (step, full action payload, execute response summary).
  - supports optional recording save (default on) to `.snowl/recordings` and exports artifact refs in agent output.

#### Runtime Artifact Plumbing (Reusable Framework Fix)
- Updated runtime engine to pass `state.output["artifacts"]` through to `TaskResult.artifacts`.
- Reuse rationale:
  - this artifact channel is generic (not OSWorld-specific) and can be shared by other benchmarks that produce files (recordings, traces, screenshots).

#### Tests Added/Updated
- `tests/test_osworld_benchmark.py`
  - extended real-container-contract test for:
    - accessibility + terminal observe fields
    - recording start/stop endpoints
    - hotkey action payload mapping
  - added action mapping coverage test for newly supported actions.
- `tests/test_runtime_engine.py`
  - added artifact passthrough test (`state.output.artifacts -> task_result.artifacts`).

### 2026-03-04 (Round 11)

#### Official Evaluator Replication (Task-JSON Driven)
- Reworked `GuiEnv.evaluate()` to support OSWorld official-style evaluator config:
  - when payload includes `evaluator`, evaluate now resolves getter/metric functions dynamically from
    `references/OSWorld/desktop_env/evaluators/*`.
  - supports both:
    - single metric (`func: "..."`)
    - multi metric (`func: ["..."]`) with `conj: and|or`, per-metric `result/expected/options`.
  - retains `infeasible` and last-action-`FAIL` handling semantics from OSWorld `DesktopEnv.evaluate`.
- Added lightweight postconfig execution path in Snowl (without requiring OSWorld `SetupController` import):
  - executes postconfig steps through `/setup/*` HTTP endpoints for common step types
    (`execute`, `execute_with_verification`, `launch`, `open`, `activate_window`, `close_window`, `change_wallpaper`, `sleep`).

#### Why Lightweight Postconfig Instead of Direct SetupController Reuse
- `desktop_env.controllers.setup.SetupController` import currently fails in local Snowl env
  because optional dependency `playwright` is missing.
- Therefore, postconfig is executed through server endpoints directly to keep evaluation working
  without forcing full host-side OSWorld setup stack.
- Also validated that bulk import of `desktop_env.evaluators.metrics` can fail locally when optional
  metric deps (e.g. `rapidfuzz`) are absent; dynamic per-function loading is now used instead.

#### Agent/Eval Wiring
- `examples/osworld-official/agent.py` now passes task evaluator metadata and action history into `env.evaluate(...)`.
- Agent trace now records evaluation diagnostics:
  - `simulated`, `mode`, `error`, `metric/metrics`, `postconfig`.

#### Validation
- Targeted tests:
  - `python -m pytest -q tests/test_osworld_benchmark.py tests/test_runtime_engine.py tests/test_osworld_container_runtime.py`
  - `17 passed`.
- Runtime smoke (evaluate path):
  - `SNOWL_OSWORLD_MAX_STEPS=0 SNOWL_OSWORLD_SAMPLE_LIMIT=1 python -m snowl.cli bench run osworld --project examples/osworld-official --split test --limit 1 --max-trials 1 --no-ui`
  - confirmed `osworld.evaluate` executes and surfaces evaluator import failure explicitly:
    - `mode=osworld_evaluator_fallback`
    - `error=No module named 'rapidfuzz'`
  - recording path also confirmed in events (`osworld.recording.saved`).

#### Dependency Ergonomics
- Added optional dependency group in `pyproject.toml`:
  - `.[osworld_eval]` for full OSWorld evaluator imports.
- Added evaluator dependency check utility:
  - `scripts/check_osworld_eval_imports.py`
  - scans dataset evaluator config -> resolves getter/metric symbols -> reports missing imports.

### 2026-03-04 (Round 12)

#### Recording Artifact Persistence Fix (Framework Reuse)
- Root cause for `recording.saved` visible in events but empty `task_result.artifacts`:
  - `runtime/engine.py` rebuilt `TaskResult` in two branches without copying `artifacts`:
    - scorer exception branch (`scorer_error`)
    - success->incorrect status transition when `accuracy < 1`
- Fix:
  - preserve `artifacts` in both `TaskResult` rebuild paths.

#### Regression Tests
- `tests/test_runtime_engine.py`:
  - added `test_execute_trial_artifacts_preserved_when_incorrect`
  - added `test_execute_trial_artifacts_preserved_when_scorer_errors`
- Validation:
  - `python -m pytest -q tests/test_runtime_engine.py` -> `8 passed`
  - `python -m pytest -q tests/test_osworld_benchmark.py tests/test_osworld_container_runtime.py` -> `11 passed`

### 2026-03-06 (Round 13)

#### Refactor Goal (Collaboration-Friendly Boundaries)
- Move OSWorld-specific setup/evaluate/container details out of shared framework modules.
- Keep `snowl/envs/gui_env.py` and `snowl/runtime/container_runtime.py` as reusable interfaces for all benchmarks.
- Place OSWorld behavior in benchmark layer (`snowl/benchmarks/osworld/*`) so future benchmark adapters do not inherit OSWorld coupling.

#### Changes
- Added OSWorld evaluator module:
  - `snowl/benchmarks/osworld/evaluator.py`
  - dynamic getter/metric loading from `references/OSWorld/desktop_env/evaluators/*`
  - task-json driven `postconfig` setup execution and evaluate semantics (`conj`, options, infeasible, FAIL handling).
- Added OSWorld container launcher:
  - `snowl/benchmarks/osworld/container.py`
  - centralizes VM cache/boot input, cap-add, dynamic port allocation/retry, and startup diagnostics.
- Simplified shared runtime/env modules:
  - `snowl/runtime/container_runtime.py` now delegates OSWorld prep to launcher module.
  - `snowl/envs/gui_env.py` now keeps generic GUI container, observation, action, and recording interfaces only.
- Adapter + agent wiring:
  - `snowl/benchmarks/osworld/adapter.py` now stores task metadata needed by evaluator/setup.
  - `examples/osworld-official/agent.py` now calls benchmark-layer setup/evaluator path.
- Toolset compatibility:
  - `snowl/tools/gui.py` adds compatibility aliases (`key`, `terminate`).

#### Test Alignment
- Added:
  - `tests/test_osworld_evaluator.py`
- Updated:
  - `tests/test_osworld_container_runtime.py`
  - `tests/test_osworld_benchmark.py`
  - `tests/test_gui_env_interaction.py` (updated to new launcher interface, default skipped unless `SNOWL_RUN_DOCKER_INTEGRATION=1`).

#### Validation
- Passed:
  - `python -m pytest -q -p no:cacheprovider tests/test_osworld_evaluator.py tests/test_osworld_container_runtime.py tests/test_osworld_benchmark.py::test_gui_env_and_built_in_tools tests/test_osworld_benchmark.py::test_gui_env_real_container_contract tests/test_osworld_benchmark.py::test_gui_env_action_mapping_coverage tests/test_osworld_benchmark.py::test_gui_env_evaluate_done_status_success tests/test_osworld_benchmark.py::test_gui_env_evaluate_done_status_failed tests/test_osworld_benchmark.py::test_osworld_official_example_modules_importable tests/test_gui_env_interaction.py`
  - result: `10 passed, 1 skipped`.
- Environment note:
  - full-suite runs including `tmp_path` fixtures are currently affected on this machine by Windows temp-dir permission errors (`WinError 5`), so final verification used fixture-independent targeted tests.

### 2026-03-06 (Round 14)

#### Prompt/Action Compatibility Check Against OSWorld Source
- Reviewed official prompt/action definitions in:
  - `references/OSWorld/mm_agents/prompts.py`
  - `references/OSWorld/mm_agents/agent.py`
- Key finding:
  - official prompt examples include legacy aliases like `TYPE`/`KEY` and top-level action fields (not always nested `parameters`), while Snowl adapter expected normalized schema only.

#### Runtime Behavior Issue Observed
- Recent run log showed:
  - container marked ready by `/screenshot` health check,
  - first observation had low-signal state (`screenshot_bytes` small, no a11y/terminal),
  - trial failed early due `Unsupported action_type: TYPE`.
- This can produce poor agent behavior when desktop is still effectively not usable.

#### Fixes
- Added OSWorld visual readiness probe in benchmark container launcher:
  - `snowl/benchmarks/osworld/container.py`
  - after HTTP-ready, poll observations with signal checks before handing env to agent.
  - configurable via:
    - `SNOWL_OSWORLD_VISUAL_READY_TIMEOUT`
    - `SNOWL_OSWORLD_VISUAL_READY_MIN_SCREENSHOT_BYTES`
    - `SNOWL_OSWORLD_VISUAL_READY_POLL_SEC`
  - defaults are longer on no-KVM hosts.
- Added action compatibility aliases in GUI env:
  - `TYPE -> TYPING`
  - `KEY -> PRESS` (or `HOTKEY` when combo detected)
  - supports top-level action fields (`text`, `key`, `x`, `y`, `click_type`, etc.) when `parameters` is absent.
- Improved example agent prompt constraints:
  - `examples/osworld-official/agent.py`
  - stricter schema instructions to avoid abstract `target` placeholders and enforce executable parameters.
- Agent robustness:
  - action execution exceptions are now recorded and continued instead of hard-crashing the whole trial immediately.

#### Validation
- Passed:
  - `python -m pytest -q -p no:cacheprovider tests/test_osworld_container_runtime.py tests/test_osworld_benchmark.py::test_gui_env_action_mapping_coverage tests/test_osworld_benchmark.py::test_osworld_official_example_modules_importable`
  - result: `6 passed`.

### 2026-03-06 (Round 15)

#### Setup Visibility Clarification
- Confirmed setup execution path in example agent:
  - `examples/osworld-official/agent.py`
  - uses `run_setup_config(...)` before action loop.
- Runtime logs now consistently show:
  - `osworld.setup` event with `steps` and `failed` fields.

#### Prompt/Input Simplification (Per OSWorld Observation Types)
- Adjusted agent model input to only include:
  - `Instruction`
  - `Observation`
- Removed large `Task Metadata` payload from model prompt context.

#### Observation Type Alignment + VLM Guard
- Added `SNOWL_OSWORLD_OBSERVATION_TYPE` with supported values:
  - `a11y_tree` (default)
  - `screenshot`
  - `screenshot_a11y_tree`
- Added strict VLM requirement for screenshot-based modes:
  - if model is non-vision and observation type includes screenshot, run fails fast with actionable message.

#### Logging Hygiene
- Model I/O event now sanitizes request payload for logs:
  - screenshot data URLs are redacted.
  - avoids oversized and noisy event payloads.

### 2026-03-06 (Round 16)

#### VLM Screenshot Delivery Debuggability Fix
- Problem observed:
  - users could see `<redacted>` in `runtime.model.io` and could not verify whether the current screenshot was truly sent to VLM.
  - occasional empty screenshot observations could cause weak/invalid VLM context.

#### Changes
- `examples/osworld-official/agent.py`:
  - dynamic observation-type default:
    - if `SNOWL_OSWORLD_OBSERVATION_TYPE` unset:
      - vision model -> `screenshot`
      - non-vision model -> `a11y_tree`
  - screenshot-mode retry:
    - when screenshot bytes are empty, retry observe before querying model.
    - new env knobs:
      - `SNOWL_OSWORLD_SCREENSHOT_RETRIES` (default `3`)
      - `SNOWL_OSWORLD_SCREENSHOT_RETRY_WAIT_SEC` (default `1.0`)
  - per-step observation frame persistence (debug):
    - default enabled for screenshot bytes.
    - saved under `.snowl/observations/<sample_id>/step_XXX.png`
    - env knobs:
      - `SNOWL_OSWORLD_SAVE_OBSERVATION_FRAMES` (default `1`)
      - `SNOWL_OSWORLD_OBS_FRAMES_DIR`
  - model I/O telemetry now includes `observation_meta`:
    - `observation_type`
    - `screenshot_bytes`
    - `screenshot_sha256`
    - optional `saved_frame` path

#### Validation
- Passed:
  - `python -m pytest -q -p no:cacheprovider tests/test_osworld_benchmark.py::test_osworld_official_example_modules_importable tests/test_osworld_benchmark.py::test_gui_env_action_mapping_coverage tests/test_osworld_container_runtime.py`
  - result: `6 passed`.

### 2026-03-06 (Round 17)

#### Official Prompt Parity Upgrade
- Goal:
  - align Snowl OSWorld example agent prompt behavior with OSWorld native `PromptAgent` as closely as practical.
- Changes in `examples/osworld-official/agent.py`:
  - system prompt now loads from official reference templates in:
    - `references/OSWorld/mm_agents/prompts.py`
    - mapping by observation type:
      - `screenshot -> SYS_PROMPT_IN_SCREENSHOT_OUT_ACTION`
      - `a11y_tree -> SYS_PROMPT_IN_A11Y_OUT_ACTION`
      - `screenshot_a11y_tree -> SYS_PROMPT_IN_BOTH_OUT_ACTION`
  - per-step user prompt now follows official wording pattern:
    - `Given the screenshot as below...`
    - `Given the info from accessibility tree as below...`
    - `Given the screenshot and info from accessibility tree as below...`
  - instruction injected into system message using official pattern:
    - `You are asked to complete the following task: ...`
  - added lightweight trajectory history stitching (`max_trajectory_length`) in message construction.
  - response parsing upgraded for official action outputs:
    - supports single action dict, fenced JSON blocks, and `WAIT/DONE/FAIL`.

#### Resolution Note
- Yes: the official prompt templates already include coordinate/screen-size guidance in their action-space instructions.
- By loading those templates directly, Snowl now inherits the same resolution-related guidance text as native OSWorld prompt flow.

### 2026-03-06 (Round 18)

#### Minimal Evaluator Requirements File
- Added benchmark-scoped minimal dependency file:
  - `snowl/benchmarks/osworld/requirements-eval-min.txt`
- Purpose:
  - avoid installing the full OSWorld root requirements when only evaluator/getter runtime is needed in Snowl.
  - cover all third-party imports from metric/getter modules referenced by OSWorld task JSON evaluators.
- Also updated install docs:
  - `examples/osworld-official/README.md` now includes:
    - `pip install -r snowl/benchmarks/osworld/requirements-eval-min.txt`
    - `python -m playwright install chromium`

### 2026-03-06 (Round 19)

#### Prompt Formatting Runtime Crash Fix
- Reproduced runtime error right after sandbox prepare:
  - message looked like `'"action_type"'` from `agent_runtime_error`.
- Root cause:
  - official prompt templates contain many JSON braces (`{...}`).
  - code used `str.format(...)` to inject `{CLIENT_PASSWORD}`, which mistakenly treated JSON braces as format fields.
- Fix:
  - `examples/osworld-official/agent.py`
  - replaced `.format(...)` with safe literal placeholder replacement via `_inject_client_password(...)`.
- Regression test added:
  - `tests/test_osworld_benchmark.py::test_osworld_official_prompt_injection_handles_json_braces`
  - validates prompt injection works without breaking JSON braces.

### 2026-03-06 (Round 20)

#### Evaluator Import-Chain Robustness Fix
- Problem observed on machine with evaluator deps installed:
  - `osworld.evaluate` fell back with:
    - `No module named 'frontend'`
    - `Directory 'static/' does not exist`
- Root cause:
  - dynamic loader imported metric/getter modules via package path, which triggers:
    - `desktop_env.evaluators.metrics.__init__`
    - `desktop_env.evaluators.getters.__init__`
  - those `__init__` files import *all* evaluator modules eagerly.
  - unrelated modules (for unused metrics) can import `fitz`/other heavy deps and fail, even when current task only needs a simple metric/getter.

#### Fix
- Updated `snowl/benchmarks/osworld/evaluator.py` loader:
  - switched to file-targeted module loading (`spec_from_file_location`) for the exact metric/getter file.
  - installed namespace-package stubs for:
    - `desktop_env`
    - `desktop_env.evaluators`
    - `desktop_env.evaluators.<category>`
  - avoids executing category `__init__.py` during targeted function load.
- Added clearer dependency-conflict hint:
  - if import chain still raises `frontend/static` signature errors, evaluator now reports actionable message to remove conflicting `fitz` and keep `pymupdf`.
- Added docs note:
  - `examples/osworld-official/README.md` troubleshooting section now documents `fitz` vs `pymupdf` conflict fix.

#### Regression Test
- Added:
  - `tests/test_osworld_evaluator.py::test_load_callable_bypasses_category_init`
- Validates:
  - loader can resolve and execute target metric function even when `metrics/__init__.py` intentionally raises.
