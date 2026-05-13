# UI API

Console renderers, UI events, and panel configuration.

## Key classes

### ConsoleRenderer

Streaming console renderer for evaluation output.

```python
from snowl.ui import ConsoleRenderer, StreamingTheme

renderer = ConsoleRenderer(
    verbose=True,
    width=None,
    streaming_theme=StreamingTheme(),
)
```

Methods:

| Method | Description |
|--------|-------------|
| `render_plan(plan)` | Render the trial plan |
| `render_global(done, total, ...)` | Render global progress |
| `render_trial_start(trial, index, total)` | Render trial start |
| `render_trial_finish(outcome)` | Render trial result |
| `render_compare(aggregate)` | Render comparison table |
| `render_controls()` | Render keyboard controls |
| `render_summary(summary, artifacts_dir, rerun_cmd)` | Render run summary |
| `render_runtime_event(event)` | Render a runtime event |

### LiveConsoleRenderer

Full-screen dashboard renderer (opt-in via `--cli-ui`).

```python
from snowl.ui import LiveConsoleRenderer

renderer = LiveConsoleRenderer(
    max_events=240,
    refresh_interval_ms=80,
    ui_mode="auto",
)
```

### StreamingTheme

Color/style theme for the streaming console renderer.

```python
from snowl.ui import StreamingTheme

theme = StreamingTheme(
    section_border="blue",
    section_title="bold cyan",
    step_number="bold yellow",
    model_name="bold magenta",
    direction_in="green",
    direction_out="cyan",
    scorer_metric="bold green",
    scorer_value="yellow",
    error="bold red",
    status_ok="green",
    status_fail="red",
)
```

### UIEvent

Normalized runtime event for the UI layer.

```python
from snowl.ui import UIEvent, EventPhase

event = UIEvent(
    run_id="run-123",
    ts_ms=1715500000000,
    phase=EventPhase.AGENT,
    event="agent.step",
    task_id="task-1",
    agent_id="react_agent",
    message="Step 1: calling tool",
)
```

### TaskMonitorState

Tracks the state of a single trial in the UI.

```python
from snowl.ui import TaskMonitorState, TaskExecutionStatus

state = TaskMonitorState(
    task_id="task-1",
    agent_id="react_agent",
    variant_id="gpt4o",
    sample_id="sample-1",
    status=TaskExecutionStatus.RUNNING,
    step_count=3,
)
```

## Enums

### EventPhase

| Value | Description |
|-------|-------------|
| `PLAN` | Planning phase |
| `ENV` | Environment setup |
| `TASK` | Task loading |
| `AGENT` | Agent execution |
| `SCORER` | Scoring |
| `ERROR` | Error |
| `CONTROL` | Control event |
| `SUMMARY` | Run summary |

### TaskExecutionStatus

| Value | Description |
|-------|-------------|
| `QUEUED` | Waiting to run |
| `RUNNING` | Currently executing |
| `SCORING` | Being scored |
| `SUCCESS` | Completed successfully |
| `INCORRECT` | Completed with incorrect result |
| `ERROR` | Completed with error |
| `CANCELLED` | Was cancelled |
| `LIMIT_EXCEEDED` | Exceeded resource limit |
