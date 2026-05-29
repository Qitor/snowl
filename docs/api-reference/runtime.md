# Runtime API Reference

## Engine Phases

Snowl's evaluation runtime executes trials through four phases:

### prepare_trial_phase

```python
async def prepare_trial_phase(request: TrialRequest) -> PreparedTrial
```

Validates task, agent, scorer, and environment. Sets up workspace, containers, sandbox, and tool specs.

### execute_agent_phase

```python
async def execute_agent_phase(prepared: PreparedTrial) -> ExecutedTrial
```

Runs the agent in the prepared environment. Handles tool execution, middleware, and step limits.

### score_trial_phase

```python
async def score_trial_phase(executed: ExecutedTrial) -> ScoredTrial
```

Applies scorers to the agent's output. Supports separated verifier mode.

### finalize_trial_phase

```python
async def finalize_trial_phase(scored: ScoredTrial) -> FinalizedTrial
```

Cleans up containers, sandbox, workspace. Collects timing and produces the final trial outcome.

## TrialRequest

```python
@dataclass
class TrialRequest:
    run_id: str
    trial_id: str
    task: Task
    agent: Agent
    scorer: Scorer
    sample: dict | Sample
    limits: TrialLimits
    tools: list[ToolSpec] | None
    sandbox_runtime: SandboxRuntime | None
    container_lifecycle: ContainerLifecycleManager | None
    mcp_servers: list[MCPServerSpec] | None
```

## RuntimePolicy

Controls runtime behavior per-evaluation:

```python
@dataclass
class RuntimePolicy:
    max_steps: int | None = None          # Max agent steps
    max_container_slots: int = 4          # Parallel containers
    max_builds: int = 2                   # Parallel container builds
    provider_budget: float | None = None  # Max spend in USD
    keep_containers: bool = False         # Keep containers after trial
    keep_failed_containers: bool = False  # Keep failed containers for debugging
```

## SandboxRuntime

```python
class SandboxRuntime:
    async def prepare(self, spec: SandboxSpec) -> PreparedSandbox
    async def cleanup(self, sandbox: PreparedSandbox) -> None
```

## VerifierReport

```python
@dataclass(frozen=True)
class VerifierReport:
    score: float
    dimensions: dict[str, float] | None = None
    confidence: str = "HIGH"    # HIGH, MEDIUM, or LOW
    environment_diff: dict[str, Any] | None = None
    raw_output: str | None = None
    retries_used: int = 0
```

## PolicyApprovalAdapter

Bridges tool-trace policy enforcement to the approval system:

```python
class PolicyApprovalAdapter:
    def __init__(self, config: ToolTracePolicyConfig)
    async def check(self, tool_call: ToolCall, context: Any) -> ApprovalDecision
```

Use with `CompositeApproval` to combine policy checks with other approval policies.
