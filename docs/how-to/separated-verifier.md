# Separated Verifier Mode

Snowl supports running verification in an **isolated container** separate from the agent environment. This prevents agents from tampering with scoring logic or results.

## When to Use

- Security-sensitive evaluations where the agent might try to manipulate scoring
- Benchmarks that require a clean environment for verification (e.g., SWE-bench, terminalbench)
- Evaluations where agent and verifier need different container images

## Configuration

In your `project.yml`:

```yaml
eval:
  verifier:
    mode: separate
    image: python:3.12-slim
    command: "python verify.py"
    timeout_seconds: 120
    resources:
      mem_limit: 512m
      cpu_count: 1
    environment:
      VERIFY_STRICT: "1"
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | string | `"shared"` | `"separate"` for isolated verification |
| `image` | string | required | Docker image for the verifier container |
| `command` | string | `"bash tests/test.sh"` | Command to execute in the verifier |
| `timeout_seconds` | float | `120.0` | Execution timeout |
| `resources` | dict | `{}` | Container resource limits (`mem_limit`, `cpu_count`, `pids_limit`) |
| `environment` | dict | `{}` | Environment variables for the verifier |
| `network` | dict | `{}` | Network configuration (`mode: "none"` for no network) |
| `build_context` | string | — | Docker build context for custom verifier images |
| `dockerfile` | string | — | Dockerfile path when using `build_context` |

## How It Works

1. **Agent phase**: The agent runs in its own environment and produces outputs
2. **Verifier prepare**: Snowl starts a separate container with the verifier image
3. **Artifact transfer**: The agent's workspace is copied into the verifier container via `docker cp`
4. **Verification**: The verifier command runs in isolation and writes a reward file
5. **Teardown**: The verifier container is removed

## Reward Format

The verifier command must produce a reward in one of these formats:

**reward.txt** — a single float on a line:
```
0.85
```

**reward.json** — structured output:
```json
{"reward": 0.85}
```

Or multi-dimensional:
```json
{"dimensions": {"correctness": 1.0, "style": 0.7, "efficiency": 0.9}}
```

## Retry Configuration

Infrastructure failures (Docker errors, timeouts) are automatically retried. Configure in code:

```python
from snowl.runtime.separated_verifier import SeparatedVerifierExecutor

executor = SeparatedVerifierExecutor(
    spec=verifier_spec,
    max_retries=2,
    retry_backoff_seconds=2.0,
)
```

Test-logic failures (non-zero exit code from the verifier command) are **not** retried.

## Confidence Assessment

Verifier results include a confidence indicator:

| Confidence | Condition |
|-----------|-----------|
| HIGH | Score is 0.0 or 1.0 with no infrastructure issues |
| MEDIUM | Score is between 0 and 1 (partial) |
| LOW | Timeout or infrastructure retry occurred |

The confidence is available in score metadata: `score.metadata["confidence"]`.
