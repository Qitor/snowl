# TerminalEnv Tmux Session Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade `TerminalEnv` so compose-backed terminal tasks can execute agent commands through a persistent tmux session, matching Terminal-Bench runtime semantics closely enough for agent state to persist across commands.

**Architecture:** Keep `TerminalEnv` as the public abstraction and add an internal tmux-session layer that is only activated for docker-compose terminal environments. Reuse the existing compose lifecycle and subprocess/event plumbing, while routing `send_keys()` and `capture()` through tmux commands inside the target container.

**Tech Stack:** Python 3.10+, `subprocess`, docker compose CLI, tmux inside benchmark containers, pytest.

---

### Task 1: Document the target behavior with failing tests

**Files:**
- Modify: `tests/test_terminalbench_benchmark.py`
- Reference: `references/terminal-bench/terminal_bench/terminal/tmux_session.py`

**Step 1: Write the failing tests**

Add tests that prove:
- compose-backed `send_keys(..., is_blocking=True)` creates and uses a tmux session instead of direct shell exec
- repeated `send_keys()` calls reuse the same tmux session
- compose-backed `capture()` reads from `tmux capture-pane`

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/data/pxd-team/workspace/fyh/snowl ./.venv/bin/python -m pytest -q tests/test_terminalbench_benchmark.py -k 'tmux_session'`

Expected: FAIL because `TerminalEnv` does not yet know how to create or reuse tmux sessions.

**Step 3: Keep test doubles minimal**

Use a fake `subprocess.Popen` implementation that can:
- capture commands invoked by `_run_subprocess`
- return different exit codes/stdout for `tmux has-session`, `tmux new-session`, `tmux send-keys`, `tmux wait`, and `tmux capture-pane`

**Step 4: Re-run the focused tests**

Run: `PYTHONPATH=/data/pxd-team/workspace/fyh/snowl ./.venv/bin/python -m pytest -q tests/test_terminalbench_benchmark.py -k 'tmux_session'`

Expected: still FAIL, but now only on the missing feature behavior.

### Task 2: Add tmux session support to TerminalEnv

**Files:**
- Modify: `snowl/envs/terminal_env.py`
- Reference: `references/terminal-bench/terminal_bench/terminal/tmux_session.py`

**Step 1: Add tmux session state to TerminalEnv**

Add fields for:
- session name
- whether tmux session has been started
- optional completion token/name for blocking waits

**Step 2: Add internal tmux helpers**

Implement helpers for:
- composing tmux commands inside the compose service
- checking whether the tmux session exists
- creating the tmux session lazily
- sending tmux keys with official-style blocking semantics
- capturing pane content
- clearing/stopping the session during teardown if needed

**Step 3: Wire compose `send_keys()` through tmux**

When `use_docker_compose=True`:
- `send_keys()` should lazily ensure the tmux session exists
- blocking commands should append the completion command and wait via `tmux wait`
- non-blocking commands should still go through `tmux send-keys`

Keep local mode unchanged.

**Step 4: Wire compose `capture()` through tmux**

When `use_docker_compose=True`, `capture()` should return `tmux capture-pane` output instead of `_last_output`.

**Step 5: Keep `exec()` / `run_tests()` semantics stable**

Do not move `run_tests()` into the tmux session in this pass. Keep it as direct exec so scorer/test execution remains isolated from the agent’s interactive shell state.

### Task 3: Verify the new runtime behavior

**Files:**
- Test: `tests/test_terminalbench_benchmark.py`

**Step 1: Run focused tmux tests**

Run: `PYTHONPATH=/data/pxd-team/workspace/fyh/snowl ./.venv/bin/python -m pytest -q tests/test_terminalbench_benchmark.py -k 'tmux_session'`

Expected: PASS

**Step 2: Run related terminal benchmark tests**

Run: `PYTHONPATH=/data/pxd-team/workspace/fyh/snowl ./.venv/bin/python -m pytest -q tests/test_terminalbench_benchmark.py`

Expected: PASS, or reveal pre-existing unrelated failures that should be reported explicitly.

**Step 3: Inspect diff**

Run: `git diff -- snowl/envs/terminal_env.py tests/test_terminalbench_benchmark.py`

Expected: changes are limited to tmux integration and test coverage.

### Task 4: Wrap up cleanly

**Files:**
- Modify: `snowl/envs/terminal_env.py`
- Modify: `tests/test_terminalbench_benchmark.py`

**Step 1: Refactor only after green**

If tests pass, do a light cleanup of helper names or duplicated command-building logic. Do not widen scope into recording, livestreaming, or docker SDK integration.

**Step 2: Final verification**

Run: `PYTHONPATH=/data/pxd-team/workspace/fyh/snowl ./.venv/bin/python -m pytest -q tests/test_terminalbench_benchmark.py -k 'tmux_session or retries_parse_error or parse_retry_exhausted'`

Expected: PASS

**Step 3: Commit**

```bash
git add docs/plans/2026-03-06-terminal-env-tmux-session.md snowl/envs/terminal_env.py tests/test_terminalbench_benchmark.py
git commit -m "feat: add tmux-backed terminal env runtime"
```
