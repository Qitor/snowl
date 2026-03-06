# Terminalbench Trajectory Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve the raw per-episode model input/output sequence for `examples/terminalbench-official` and surface it in `outcomes.json` as `task_result.final_output.traj`.

**Architecture:** Keep the change minimal and faithful to current runtime behavior. The terminalbench official agent will append one `user` message for each prompt it sends to the model and one `assistant` message for each raw model response it receives. The runtime engine will pass through an optional `traj` field from `state.output` into `task_result.final_output`, which automatically makes it appear in `outcomes.json` and `trials.jsonl` without changing the serializer.

**Tech Stack:** Python, pytest, existing `snowl` runtime/result serialization.

---

### Task 1: Lock the desired agent behavior with tests

**Files:**
- Modify: `tests/test_terminalbench_benchmark.py`

**Step 1: Write the failing test**
Add a test that runs `TerminusOfficialAgent` with a fake model response and asserts `state.output["traj"]` contains the raw `user` prompt followed by the raw `assistant` content.

**Step 2: Run test to verify it fails**
Run: `PYTHONPATH=/data/pxd-team/workspace/fyh/snowl ./.venv/bin/python -m pytest -q tests/test_terminalbench_benchmark.py -k traj`
Expected: FAIL because `traj` is not recorded.

**Step 3: Write minimal implementation**
Update `examples/terminalbench-official/agent.py` to accumulate raw prompt/response messages per model call and store them under `state.output["traj"]`.

**Step 4: Run test to verify it passes**
Run the same pytest command and confirm the new test passes.

### Task 2: Lock the runtime serialization behavior with tests

**Files:**
- Modify: `tests/test_eval_artifact_schema.py`
- Modify: `snowl/runtime/engine.py`

**Step 1: Write the failing test**
Extend the eval artifact schema test so the inline agent returns `state.output["traj"]`, then assert `outcomes.json` contains `task_result.final_output.traj`.

**Step 2: Run test to verify it fails**
Run: `PYTHONPATH=/data/pxd-team/workspace/fyh/snowl ./.venv/bin/python -m pytest -q tests/test_eval_artifact_schema.py`
Expected: FAIL because runtime engine drops `traj`.

**Step 3: Write minimal implementation**
Update `snowl/runtime/engine.py` to include `traj` in `final_output` when present.

**Step 4: Run test to verify it passes**
Run the same pytest command and confirm it passes.

### Task 3: Full verification

**Files:**
- Modify: `examples/terminalbench-official/agent.py`
- Modify: `snowl/runtime/engine.py`
- Modify: `tests/test_terminalbench_benchmark.py`
- Modify: `tests/test_eval_artifact_schema.py`

**Step 1: Run focused regression checks**
Run: `PYTHONPATH=/data/pxd-team/workspace/fyh/snowl ./.venv/bin/python -m pytest -q tests/test_terminalbench_benchmark.py -k traj`
Expected: PASS.

**Step 2: Run serialization regression checks**
Run: `PYTHONPATH=/data/pxd-team/workspace/fyh/snowl ./.venv/bin/python -m pytest -q tests/test_eval_artifact_schema.py`
Expected: PASS.

**Step 3: Run broader safety check**
Run: `PYTHONPATH=/data/pxd-team/workspace/fyh/snowl ./.venv/bin/python -m pytest -q tests/test_terminalbench_benchmark.py tests/test_eval_artifact_schema.py`
Expected: PASS.
