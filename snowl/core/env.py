"""Core environment contract for capability declaration and sandbox spec hashing.

Framework role:
- Defines env capability protocols (`FileOps`, `ProcessOps`, `WebOps`) and `EnvSpec`/`SandboxSpec` data contracts.
- `SandboxSpec.spec_hash()` provides deterministic identity used by runtime pooling/locality logic.

Runtime/usage wiring:
- Consumed by task definitions, runtime engine validation, and sandbox/container preparation layers.

Change guardrails:
- Canonicalization/hash behavior must stay stable unless migration is intentional and documented.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

from snowl.core.mcp import MCPServerSpec, validate_mcp_server_spec
from snowl.errors import SnowlValidationError


@runtime_checkable
class FileOps(Protocol):
    def read_file(self, path: str) -> str: ...

    def write_file(self, path: str, content: str) -> None: ...

    def list_files(self, path: str) -> list[str]: ...


@runtime_checkable
class ProcessOps(Protocol):
    def run_command(self, command: str, timeout_seconds: float | None = None) -> str: ...


@runtime_checkable
class WebOps(Protocol):
    def fetch_url(self, url: str) -> str: ...


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _canonicalize(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    if isinstance(value, tuple):
        return [_canonicalize(v) for v in value]
    return value


@dataclass(frozen=True)
class SandboxSpec:
    provider: str = "local"
    image: str | None = None
    build_context: str | None = None
    dockerfile: str | None = None
    resources: dict[str, Any] = field(default_factory=dict)
    network: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    volumes: list[dict[str, Any]] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> dict[str, Any]:
        build_context = self.build_context
        if build_context:
            build_context = os.path.normpath(build_context)

        data = {
            "provider": self.provider,
            "image": self.image,
            "build_context": build_context,
            "dockerfile": self.dockerfile,
            "resources": self.resources,
            "network": self.network,
            "environment": self.environment,
            "volumes": self.volumes,
            "command": self.command,
            "metadata": self.metadata,
        }
        return _canonicalize(data)

    def spec_hash(self) -> str:
        normalized_json = json.dumps(
            self.normalized(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()


class VerifierMode(str, Enum):
    """Whether scoring runs in the same process or a separate isolated container."""

    SHARED = "shared"
    SEPARATE = "separate"


@dataclass(frozen=True)
class VerifierSpec:
    """Configuration for running a verifier in an isolated container.

    Attributes:
        mode: SHARED (in-process, default) or SEPARATE (isolated container).
        image: Docker image for the verifier container (SEPARATE mode).
        build_context: Docker build context directory (alternative to image).
        dockerfile: Dockerfile path within build_context.
        command: Default verification command(s).
        environment: Environment variables for the verifier container.
        resources: Resource limits (CPU, memory, etc.).
        network: Network configuration (default: isolated).
        priority_scorers: Scorer IDs that should run in separated mode.
        timeout_seconds: Command execution timeout.
        metadata: Arbitrary metadata for verifier configuration.
    """

    mode: VerifierMode = VerifierMode.SHARED
    image: str | None = None
    build_context: str | None = None
    dockerfile: str | None = None
    command: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    network: dict[str, Any] = field(default_factory=dict)
    priority_scorers: tuple[str, ...] = ()
    timeout_seconds: float = 120.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def spec_hash(self) -> str:
        """Deterministic hash for verifier container pooling."""
        data = {
            "mode": self.mode.value,
            "image": self.image,
            "build_context": self.build_context,
            "dockerfile": self.dockerfile,
            "command": self.command,
            "environment": self.environment,
            "resources": self.resources,
            "network": self.network,
            "priority_scorers": list(self.priority_scorers),
            "timeout_seconds": self.timeout_seconds,
        }
        normalized = _canonicalize(data)
        normalized_json = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()


def validate_verifier_spec(spec: VerifierSpec) -> None:
    """Validate a VerifierSpec, raising SnowlValidationError on problems."""
    if not isinstance(spec, VerifierSpec):
        raise SnowlValidationError("VerifierSpec must be a VerifierSpec instance.")
    if not isinstance(spec.mode, VerifierMode):
        raise SnowlValidationError("VerifierSpec.mode must be a VerifierMode enum value.")
    if spec.mode == VerifierMode.SEPARATE:
        if not spec.image and not spec.build_context:
            raise SnowlValidationError(
                "VerifierSpec in SEPARATE mode requires either 'image' or 'build_context'."
            )
    if spec.timeout_seconds <= 0:
        raise SnowlValidationError("VerifierSpec.timeout_seconds must be > 0.")


@dataclass(frozen=True)
class EnvSpec:
    """Declares environment capability contracts for a task."""

    env_type: str
    provided_ops: tuple[str, ...] = field(default_factory=tuple)
    sandbox_spec: SandboxSpec | None = None
    config: dict[str, Any] = field(default_factory=dict)
    mcp_servers: tuple[MCPServerSpec, ...] = field(default_factory=tuple)


def validate_env_spec(env_spec: EnvSpec) -> None:
    if not isinstance(env_spec.env_type, str) or not env_spec.env_type.strip():
        raise SnowlValidationError("EnvSpec.env_type must be a non-empty string.")

    for op in env_spec.provided_ops:
        if not isinstance(op, str) or not op.strip():
            raise SnowlValidationError("EnvSpec.provided_ops must contain non-empty op names.")

    if env_spec.sandbox_spec is not None and not isinstance(env_spec.sandbox_spec, SandboxSpec):
        raise SnowlValidationError("EnvSpec.sandbox_spec must be a SandboxSpec instance.")

    for mcp_spec in env_spec.mcp_servers:
        validate_mcp_server_spec(mcp_spec)


def ensure_tool_ops_compatible(required_ops: set[str], provided_ops: set[str]) -> set[str]:
    return {op for op in required_ops if op not in provided_ops}


# ---------------------------------------------------------------------------
# Health status
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HealthStatus:
    """Result of an environment healthcheck.

    Inspired by Docker-style health checks: each check returns a ready/not-ready
    status with individual check results and an optional message.
    """
    ready: bool
    checks: dict[str, bool] = field(default_factory=dict)
    message: str | None = None


@runtime_checkable
class HealthcheckProvider(Protocol):
    """Protocol for environment providers that support health checks."""

    async def healthcheck(self, env_id: str) -> HealthStatus:
        """Check whether an environment is healthy and ready for use.

        Args:
            env_id: Identifier for the environment instance.

        Returns:
            A HealthStatus indicating readiness and individual check results.
        """
        ...
