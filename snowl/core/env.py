"""Environment, Ops contracts, and sandbox spec normalization."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

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


@dataclass(frozen=True)
class EnvSpec:
    """Declares environment capability contracts for a task."""

    env_type: str
    provided_ops: tuple[str, ...] = field(default_factory=tuple)
    sandbox_spec: SandboxSpec | None = None
    config: dict[str, Any] = field(default_factory=dict)


def validate_env_spec(env_spec: EnvSpec) -> None:
    if not isinstance(env_spec.env_type, str) or not env_spec.env_type.strip():
        raise SnowlValidationError("EnvSpec.env_type must be a non-empty string.")

    for op in env_spec.provided_ops:
        if not isinstance(op, str) or not op.strip():
            raise SnowlValidationError("EnvSpec.provided_ops must contain non-empty op names.")

    if env_spec.sandbox_spec is not None and not isinstance(env_spec.sandbox_spec, SandboxSpec):
        raise SnowlValidationError("EnvSpec.sandbox_spec must be a SandboxSpec instance.")


def ensure_tool_ops_compatible(required_ops: set[str], provided_ops: set[str]) -> set[str]:
    return {op for op in required_ops if op not in provided_ops}
