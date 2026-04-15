"""Runtime-owned registry and cleanup orchestration for benchmark container resources.

Framework role:
- Makes runtime, not benchmark agents, the source of truth for container ownership and teardown.
- Tracks per-run/per-trial runtime-owned resources so cleanup can be explicit and observable.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class ContainerLifecycleState(str, Enum):
    CREATED = "CREATED"
    LEASED = "LEASED"
    IDLE_WARM = "IDLE_WARM"
    DIRTY = "DIRTY"
    RECYCLING = "RECYCLING"
    DESTROYED = "DESTROYED"
    CLEANUP_FAILED = "CLEANUP_FAILED"


@dataclass
class RuntimeOwnedResourceRecord:
    resource_id: str
    resource_type: str
    run_id: str | None
    trial_id: str | None
    benchmark: str
    provider_name: str
    spec_hash: str | None
    lifecycle_state: ContainerLifecycleState
    cleanup_policy: str
    debug_preserve: bool
    created_at_ms: int
    last_used_at_ms: int
    lease_owner_trial_id: str | None = None
    container_id: str | None = None
    compose_project: str | None = None
    compose_file: str | None = None
    session_kind: str | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    teardown_error: str | None = None
    teardown_result: dict[str, Any] | None = None
    destroyed_at_ms: int | None = None
    released_at_ms: int | None = None
    outcome_status: str | None = None


class RuntimeContainerLifecycleManager:
    def __init__(
        self,
        *,
        run_id: str | None,
        emit: Callable[[dict[str, Any]], None] | None = None,
        keep_containers: bool = False,
        keep_failed_containers: bool = False,
    ) -> None:
        self._run_id = run_id
        self._emit = emit if callable(emit) else None
        self._keep_containers = bool(keep_containers)
        self._keep_failed_containers = bool(keep_failed_containers)
        self._lock = threading.Lock()
        self._records: dict[str, RuntimeOwnedResourceRecord] = {}
        self._teardowns: dict[str, Callable[[], Awaitable[dict[str, Any] | None]]] = {}
        self._stats = {
            "containers_created": 0,
            "containers_leased": 0,
            "containers_reused": 0,
            "containers_destroyed": 0,
            "cleanup_failures": 0,
            "containers_preserved": 0,
        }

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _emit_event(self, event: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(dict(event))
        except Exception:
            return

    def register_container(
        self,
        *,
        trial_id: str | None,
        benchmark: str,
        provider_name: str,
        spec_hash: str | None,
        cleanup_policy: str,
        debug_preserve: bool,
        container_id: str | None,
        compose_project: str | None,
        compose_file: str | None,
        session_kind: str | None,
        provider_metadata: dict[str, Any] | None,
        teardown: Callable[[], Awaitable[dict[str, Any] | None]],
    ) -> str:
        now_ms = self._now_ms()
        resource_id = f"container-{uuid.uuid4().hex[:12]}"
        record = RuntimeOwnedResourceRecord(
            resource_id=resource_id,
            resource_type="container",
            run_id=self._run_id,
            trial_id=trial_id,
            benchmark=str(benchmark or ""),
            provider_name=str(provider_name or ""),
            spec_hash=str(spec_hash) if spec_hash else None,
            lifecycle_state=ContainerLifecycleState.CREATED,
            cleanup_policy=str(cleanup_policy or "destroy_on_release"),
            debug_preserve=bool(debug_preserve),
            created_at_ms=now_ms,
            last_used_at_ms=now_ms,
            lease_owner_trial_id=trial_id,
            container_id=str(container_id) if container_id else None,
            compose_project=str(compose_project) if compose_project else None,
            compose_file=str(compose_file) if compose_file else None,
            session_kind=str(session_kind) if session_kind else None,
            provider_metadata=dict(provider_metadata or {}),
        )
        with self._lock:
            self._records[resource_id] = record
            self._teardowns[resource_id] = teardown
            self._stats["containers_created"] += 1
        self._emit_event(
            {
                "event": "runtime.resource.registered",
                "phase": "prepare",
                "resource_id": resource_id,
                "resource_type": "container",
                "run_id": self._run_id,
                "trial_id": trial_id,
                "benchmark": record.benchmark,
                "provider_name": record.provider_name,
                "spec_hash": record.spec_hash,
                "container_id": record.container_id,
                "compose_project": record.compose_project,
                "compose_file": record.compose_file,
                "session_kind": record.session_kind,
                "cleanup_policy": record.cleanup_policy,
                "debug_preserve": record.debug_preserve,
            }
        )
        return resource_id

    def lease_resource(self, resource_id: str, *, trial_id: str | None) -> None:
        now_ms = self._now_ms()
        with self._lock:
            record = self._records.get(resource_id)
            if record is None:
                return
            record.lifecycle_state = ContainerLifecycleState.LEASED
            record.lease_owner_trial_id = trial_id
            record.last_used_at_ms = now_ms
            self._stats["containers_leased"] += 1
        self._emit_event(
            {
                "event": "runtime.resource.leased",
                "phase": "prepare",
                "resource_id": resource_id,
                "trial_id": trial_id,
            }
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records.values())
            stats = dict(self._stats)
        survivors = [
            {
                "resource_id": record.resource_id,
                "trial_id": record.trial_id,
                "benchmark": record.benchmark,
                "provider_name": record.provider_name,
                "spec_hash": record.spec_hash,
                "container_id": record.container_id,
                "compose_project": record.compose_project,
                "session_kind": record.session_kind,
                "lifecycle_state": record.lifecycle_state.value,
                "debug_preserve": record.debug_preserve,
                "cleanup_policy": record.cleanup_policy,
                "teardown_error": record.teardown_error,
            }
            for record in records
            if record.lifecycle_state != ContainerLifecycleState.DESTROYED
        ]
        return {
            **stats,
            "suspected_leaked_resources": sum(
                1
                for item in survivors
                if not bool(item.get("debug_preserve"))
                and item.get("lifecycle_state") != ContainerLifecycleState.DESTROYED.value
            ),
            "surviving_resources": survivors,
        }

    def _should_preserve(self, record: RuntimeOwnedResourceRecord, *, outcome_status: str | None) -> bool:
        if self._keep_containers or record.debug_preserve:
            return True
        if self._keep_failed_containers and str(outcome_status or "").strip().lower() in {
            "error",
            "limit_exceeded",
            "cancelled",
            "incorrect",
        }:
            return True
        return False

    async def _teardown_resource(self, record: RuntimeOwnedResourceRecord, *, reason: str, phase: str) -> None:
        teardown = self._teardowns.get(record.resource_id)
        if teardown is None:
            return
        self._emit_event(
            {
                "event": "runtime.resource.teardown.start",
                "phase": phase,
                "resource_id": record.resource_id,
                "trial_id": record.trial_id,
                "reason": reason,
                "container_id": record.container_id,
                "compose_project": record.compose_project,
            }
        )
        with self._lock:
            if record.lifecycle_state == ContainerLifecycleState.DESTROYED:
                return
            record.lifecycle_state = ContainerLifecycleState.RECYCLING
        try:
            result = await teardown()
            now_ms = self._now_ms()
            with self._lock:
                if record.lifecycle_state != ContainerLifecycleState.DESTROYED:
                    record.lifecycle_state = ContainerLifecycleState.DESTROYED
                    record.destroyed_at_ms = now_ms
                    record.teardown_result = dict(result or {})
                    self._stats["containers_destroyed"] += 1
            self._emit_event(
                {
                    "event": "runtime.resource.teardown.finish",
                    "phase": phase,
                    "resource_id": record.resource_id,
                    "trial_id": record.trial_id,
                    "reason": reason,
                    "result": dict(result or {}),
                }
            )
        except Exception as exc:
            with self._lock:
                record.lifecycle_state = ContainerLifecycleState.CLEANUP_FAILED
                record.teardown_error = str(exc)
                self._stats["cleanup_failures"] += 1
            self._emit_event(
                {
                    "event": "runtime.resource.teardown.failed",
                    "phase": phase,
                    "resource_id": record.resource_id,
                    "trial_id": record.trial_id,
                    "reason": reason,
                    "message": str(exc),
                }
            )

    async def release_resource(
        self,
        resource_id: str,
        *,
        trial_id: str | None,
        outcome_status: str | None,
        reason: str = "trial_finalize",
    ) -> None:
        with self._lock:
            record = self._records.get(resource_id)
            if record is None:
                return
            if record.lifecycle_state == ContainerLifecycleState.DESTROYED:
                return
            already_preserved = bool(record.debug_preserve)
            record.last_used_at_ms = self._now_ms()
            record.released_at_ms = record.last_used_at_ms
            record.lease_owner_trial_id = None
            record.outcome_status = str(outcome_status or "").strip().lower() or None
            preserve = self._should_preserve(record, outcome_status=record.outcome_status)
            if preserve:
                record.debug_preserve = True
                record.lifecycle_state = ContainerLifecycleState.DIRTY
                if not already_preserved:
                    self._stats["containers_preserved"] += 1
            else:
                record.lifecycle_state = ContainerLifecycleState.DIRTY
        self._emit_event(
            {
                "event": "runtime.resource.released",
                "phase": "finalize",
                "resource_id": resource_id,
                "trial_id": trial_id,
                "outcome_status": outcome_status,
                "debug_preserve": preserve,
            }
        )
        if preserve:
            return
        await self._teardown_resource(record, reason=reason, phase="finalize")

    async def cleanup_run(self, *, reason: str = "run_end") -> dict[str, Any]:
        self._emit_event(
            {
                "event": "runtime.cleanup.barrier.start",
                "phase": "finalize",
                "run_id": self._run_id,
                "reason": reason,
            }
        )
        with self._lock:
            candidates = [
                record
                for record in self._records.values()
                if record.lifecycle_state != ContainerLifecycleState.DESTROYED
            ]
        for record in candidates:
            if self._should_preserve(record, outcome_status=record.outcome_status):
                with self._lock:
                    if not record.debug_preserve:
                        self._stats["containers_preserved"] += 1
                    record.debug_preserve = True
                continue
            await self._teardown_resource(record, reason=reason, phase="finalize")
        summary = self.snapshot()
        if summary.get("suspected_leaked_resources", 0) > 0:
            self._emit_event(
                {
                    "event": "runtime.cleanup.leak_suspected",
                    "phase": "finalize",
                    "run_id": self._run_id,
                    "summary": summary,
                }
            )
        self._emit_event(
            {
                "event": "runtime.cleanup.barrier.finish",
                "phase": "finalize",
                "run_id": self._run_id,
                "reason": reason,
                "summary": summary,
            }
        )
        return summary


__all__ = [
    "ContainerLifecycleState",
    "RuntimeContainerLifecycleManager",
    "RuntimeOwnedResourceRecord",
]
