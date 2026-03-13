"""Sandbox lifecycle implementations: prepare/run/teardown protocol plus local pool wrappers.

Framework role:
- Defines runtime sandbox interface and concrete local runtimes (plain, warm-pool reuse, bounded concurrency).
- Encodes pooling/reuse semantics keyed by sandbox spec hash.

Runtime/usage wiring:
- Used by runtime engine when tasks declare sandbox specs in `EnvSpec`.

Change guardrails:
- Pooling or semaphore semantics changes impact concurrency and reproducibility; validate runtime traces after edits.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol
import asyncio

from snowl.core.env import SandboxSpec


@dataclass(frozen=True)
class PreparedSandbox:
    sandbox_id: str
    spec_hash: str
    provider: str
    prepared_at_ms: int
    diagnostics: dict[str, Any] = field(default_factory=dict)


class SandboxRuntime(Protocol):
    async def prepare(self, spec: SandboxSpec) -> PreparedSandbox: ...

    async def run(
        self,
        prepared: PreparedSandbox,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any: ...

    async def teardown(self, prepared: PreparedSandbox) -> dict[str, Any]: ...


class LocalSandboxRuntime:
    """MVP concrete runtime for two-phase lifecycle; no external container backend yet."""

    async def prepare(self, spec: SandboxSpec) -> PreparedSandbox:
        now_ms = int(time.time() * 1000)
        spec_hash = spec.spec_hash()
        return PreparedSandbox(
            sandbox_id=f"{spec.provider}-{spec_hash[:12]}",
            spec_hash=spec_hash,
            provider=spec.provider,
            prepared_at_ms=now_ms,
            diagnostics={"phase": "prepare", "normalized_spec": spec.normalized()},
        )

    async def run(
        self,
        prepared: PreparedSandbox,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        _ = prepared
        return await operation()

    async def teardown(self, prepared: PreparedSandbox) -> dict[str, Any]:
        now_ms = int(time.time() * 1000)
        return {
            "sandbox_id": prepared.sandbox_id,
            "spec_hash": prepared.spec_hash,
            "provider": prepared.provider,
            "teardown_at_ms": now_ms,
            "phase": "teardown",
        }


class WarmPoolSandboxRuntime(LocalSandboxRuntime):
    """Warm pool runtime keyed by sandbox spec hash for reuse across trials."""

    def __init__(self, max_pool_size: int = 16) -> None:
        self._pool: dict[str, list[PreparedSandbox]] = {}
        self._max_pool_size = max_pool_size
        self._stats = {"prepared_new": 0, "reused": 0, "returned": 0, "evicted": 0}

    async def prepare(self, spec: SandboxSpec) -> PreparedSandbox:
        spec_hash = spec.spec_hash()
        bucket = self._pool.get(spec_hash, [])
        if bucket:
            prepared = bucket.pop()
            self._pool[spec_hash] = bucket
            self._stats["reused"] += 1
            return PreparedSandbox(
                sandbox_id=prepared.sandbox_id,
                spec_hash=prepared.spec_hash,
                provider=prepared.provider,
                prepared_at_ms=prepared.prepared_at_ms,
                diagnostics={**prepared.diagnostics, "reused": True},
            )

        self._stats["prepared_new"] += 1
        prepared = await super().prepare(spec)
        return PreparedSandbox(
            sandbox_id=prepared.sandbox_id,
            spec_hash=prepared.spec_hash,
            provider=prepared.provider,
            prepared_at_ms=prepared.prepared_at_ms,
            diagnostics={**prepared.diagnostics, "reused": False},
        )

    async def teardown(self, prepared: PreparedSandbox) -> dict[str, Any]:
        bucket = self._pool.setdefault(prepared.spec_hash, [])
        if len(bucket) < self._max_pool_size:
            bucket.append(prepared)
            self._stats["returned"] += 1
            return {
                "sandbox_id": prepared.sandbox_id,
                "spec_hash": prepared.spec_hash,
                "provider": prepared.provider,
                "phase": "teardown",
                "pooled": True,
            }

        self._stats["evicted"] += 1
        base = await super().teardown(prepared)
        base["pooled"] = False
        return base

    def stats(self) -> dict[str, int]:
        return dict(self._stats)


class BoundedSandboxRuntime:
    """Sandbox runtime wrapper limiting concurrently active sandboxes."""

    def __init__(self, inner: SandboxRuntime, max_active: int) -> None:
        self._inner = inner
        self._max_active = max(1, int(max_active))
        self._sem = asyncio.Semaphore(self._max_active)

    async def prepare(self, spec: SandboxSpec) -> PreparedSandbox:
        await self._sem.acquire()
        try:
            return await self._inner.prepare(spec)
        except Exception:
            self._sem.release()
            raise

    async def run(
        self,
        prepared: PreparedSandbox,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        return await self._inner.run(prepared, operation)

    async def teardown(self, prepared: PreparedSandbox) -> dict[str, Any]:
        try:
            return await self._inner.teardown(prepared)
        finally:
            self._sem.release()
