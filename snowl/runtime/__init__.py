"""Runtime package facade for trial execution, container bridges, and scheduler primitives.

Framework role:
- Re-exports execution request/outcome types and helper entrypoints used by eval and tests.

Runtime/usage wiring:
- Serves as the import layer for code that executes trials without binding to internal module structure.

Change guardrails:
- Export only stable runtime interfaces; avoid exposing transitional helpers by default.
"""

from snowl.envs.sandbox_runtime import (
    LocalSandboxRuntime,
    PreparedSandbox,
    SandboxRuntime,
    WarmPoolSandboxRuntime,
)
from snowl.runtime.container_runtime import ContainerRuntime, ContainerSession
from snowl.runtime.engine import (
    PartialTrialResult,
    TrialLimits,
    TrialOutcome,
    TrialRequest,
    execute_agent_phase,
    execute_trial,
    score_trial_phase,
)
from snowl.runtime.resource_scheduler import ResourceLimits, ResourceScheduler

__all__ = [
    "LocalSandboxRuntime",
    "PreparedSandbox",
    "SandboxRuntime",
    "WarmPoolSandboxRuntime",
    "ContainerRuntime",
    "ContainerSession",
    "ResourceLimits",
    "ResourceScheduler",
    "PartialTrialResult",
    "TrialLimits",
    "TrialOutcome",
    "TrialRequest",
    "execute_agent_phase",
    "execute_trial",
    "score_trial_phase",
]
