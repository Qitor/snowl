"""Task-declared runtime container contract normalization.

Framework role:
- Defines the normalized contract that tells runtime whether a trial needs a runtime-managed container.
- Merges task-level defaults with sample-level overrides so provider code can rely on one resolved input.

Runtime/usage wiring:
- Used by `ContainerRuntime` during prepare to decide provider ownership, startup settings, and cleanup policy.
- Container-backed agents should consume only the runtime-injected session produced from this contract.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(k): v for k, v in value.items()}
    return {}


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(value[key]) for key in sorted(value.keys(), key=lambda x: str(x))}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, tuple):
        return [_canonicalize(item) for item in value]
    return value


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = {str(k): v for k, v in base.items()}
    for key, value in override.items():
        target_key = str(key)
        base_value = merged.get(target_key)
        if isinstance(base_value, Mapping) and isinstance(value, Mapping):
            merged[target_key] = _deep_merge(base_value, value)
        else:
            merged[target_key] = value
    return merged


@dataclass(frozen=True)
class RuntimeContainerSpec:
    benchmark: str
    provider_name: str
    requires_container: bool
    cleanup_policy: str = "destroy_on_release"
    debug_preserve_default: bool = False
    startup: dict[str, Any] = field(default_factory=dict)
    workspace: dict[str, Any] = field(default_factory=dict)
    init_command: str | None = None
    start_command: str | None = None
    check_command: str | None = None
    network: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    mounts: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    resource_limits: dict[str, Any] = field(default_factory=dict)
    spec_hash_basis: dict[str, Any] = field(default_factory=dict)
    task_config: dict[str, Any] = field(default_factory=dict)
    sample_config: dict[str, Any] = field(default_factory=dict)

    @property
    def spec_hash(self) -> str | None:
        if not self.requires_container:
            return None
        basis = self.spec_hash_basis or {
            "benchmark": self.benchmark,
            "provider_name": self.provider_name,
            "startup": self.startup,
        }
        normalized = _canonicalize(basis)
        payload = json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_metadata(self) -> dict[str, Any]:
        return {
            "benchmark": self.benchmark,
            "provider_name": self.provider_name,
            "requires_container": self.requires_container,
            "cleanup_policy": self.cleanup_policy,
            "debug_preserve_default": self.debug_preserve_default,
            "startup": _canonicalize(self.startup),
            "workspace": _canonicalize(self.workspace),
            "init_command": self.init_command,
            "start_command": self.start_command,
            "check_command": self.check_command,
            "network": self.network,
            "env": _canonicalize(self.env),
            "mounts": _canonicalize(self.mounts),
            "artifacts": list(self.artifacts),
            "resource_limits": _canonicalize(self.resource_limits),
            "spec_hash_basis": _canonicalize(self.spec_hash_basis),
            "spec_hash": self.spec_hash,
        }


def resolve_runtime_container_spec(
    *,
    task_metadata: Mapping[str, Any] | None,
    sample: Mapping[str, Any] | None,
) -> RuntimeContainerSpec:
    task_meta = _as_mapping(task_metadata)
    sample_row = _as_mapping(sample)
    sample_meta = _as_mapping(sample_row.get("metadata"))
    task_contract = _as_mapping(task_meta.get("runtime_container"))
    sample_contract = _as_mapping(sample_meta.get("runtime_container"))

    benchmark = str(
        sample_contract.get("benchmark")
        or task_contract.get("benchmark")
        or task_meta.get("benchmark")
        or ""
    ).strip().lower()
    provider_name = str(
        sample_contract.get("provider_name")
        or task_contract.get("provider_name")
        or benchmark
        or ""
    ).strip().lower()
    requires_container = bool(
        sample_contract.get(
            "requires_container",
            task_contract.get("requires_container", False),
        )
    )
    cleanup_policy = str(
        sample_contract.get("cleanup_policy")
        or task_contract.get("cleanup_policy")
        or "destroy_on_release"
    ).strip().lower() or "destroy_on_release"
    debug_preserve_default = bool(
        sample_contract.get(
            "debug_preserve_default",
            task_contract.get("debug_preserve_default", False),
        )
    )
    task_startup = _as_mapping(task_contract.get("startup"))
    sample_startup = _as_mapping(sample_contract.get("startup"))
    startup = _deep_merge(task_startup, sample_startup)
    workspace = _deep_merge(
        _as_mapping(task_contract.get("workspace")),
        _as_mapping(sample_contract.get("workspace")),
    )
    init_command = (
        sample_contract.get("init_command")
        or task_contract.get("init_command")
        or startup.get("init_command")
    )
    start_command = (
        sample_contract.get("start_command")
        or task_contract.get("start_command")
        or startup.get("start_command")
    )
    check_command = (
        sample_contract.get("check_command")
        or task_contract.get("check_command")
        or startup.get("check_command")
        or startup.get("verification_command")
    )
    network = (
        sample_contract.get("network")
        or task_contract.get("network")
        or startup.get("network")
    )
    env = _deep_merge(
        _as_mapping(task_contract.get("env")),
        _as_mapping(sample_contract.get("env")),
    )
    env = _deep_merge(env, _as_mapping(startup.get("env")))
    mounts_raw = sample_contract.get("mounts", task_contract.get("mounts", startup.get("mounts", [])))
    mounts = [dict(item) for item in mounts_raw] if isinstance(mounts_raw, list) else []
    artifacts_raw = sample_contract.get("artifacts", task_contract.get("artifacts", startup.get("artifacts", [])))
    if isinstance(artifacts_raw, str):
        artifacts = [artifacts_raw]
    elif isinstance(artifacts_raw, list):
        artifacts = [str(item) for item in artifacts_raw if str(item).strip()]
    else:
        artifacts = []
    resource_limits = _deep_merge(
        _as_mapping(task_contract.get("resource_limits")),
        _as_mapping(sample_contract.get("resource_limits")),
    )

    task_basis = _as_mapping(task_contract.get("spec_hash_basis"))
    sample_basis = _as_mapping(sample_contract.get("spec_hash_basis"))
    spec_hash_basis = _deep_merge(task_basis, sample_basis)
    if not spec_hash_basis and requires_container:
        spec_hash_basis = {
            "benchmark": benchmark,
            "provider_name": provider_name,
            "startup": startup,
        }

    return RuntimeContainerSpec(
        benchmark=benchmark,
        provider_name=provider_name,
        requires_container=requires_container,
        cleanup_policy=cleanup_policy,
        debug_preserve_default=debug_preserve_default,
        startup=startup,
        workspace=workspace,
        init_command=(str(init_command) if init_command else None),
        start_command=(str(start_command) if start_command else None),
        check_command=(str(check_command) if check_command else None),
        network=(str(network).strip().lower() if network else None),
        env={str(k): str(v) for k, v in env.items()},
        mounts=mounts,
        artifacts=artifacts,
        resource_limits=resource_limits,
        spec_hash_basis=spec_hash_basis,
        task_config=task_contract,
        sample_config=sample_contract,
    )


__all__ = ["RuntimeContainerSpec", "resolve_runtime_container_spec"]
