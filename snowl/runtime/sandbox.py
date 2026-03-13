"""Legacy import shim for sandbox runtime classes.

Framework role:
- Re-exports sandbox runtime implementations from `snowl.envs.sandbox_runtime` for backward compatibility.

Runtime/usage wiring:
- Keeps older import paths working while runtime code migrates toward env-layer ownership.

Change guardrails:
- Do not add runtime logic here; keep it as a compatibility facade only.
"""

from snowl.envs.sandbox_runtime import (
    BoundedSandboxRuntime,
    LocalSandboxRuntime,
    PreparedSandbox,
    SandboxRuntime,
    WarmPoolSandboxRuntime,
)

__all__ = [
    "BoundedSandboxRuntime",
    "LocalSandboxRuntime",
    "PreparedSandbox",
    "SandboxRuntime",
    "WarmPoolSandboxRuntime",
]
