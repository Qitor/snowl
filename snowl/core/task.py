"""Task contracts, decorator helpers, and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Mapping, Protocol, runtime_checkable

from snowl.core.declarations import declare
from snowl.core.env import EnvSpec, validate_env_spec
from snowl.errors import SnowlValidationError


SampleData = Mapping[str, Any]
SampleIterator = Iterator[SampleData]


@dataclass(frozen=True)
class Task:
    """Concrete task definition consumed by runtime."""

    task_id: str
    env_spec: EnvSpec
    sample_iter_factory: Callable[[], SampleIterator]
    metadata: dict[str, Any] = field(default_factory=dict)

    def iter_samples(self) -> SampleIterator:
        return self.sample_iter_factory()


@runtime_checkable
class TaskProvider(Protocol):
    """Benchmark/taskset provider contract."""

    def list_splits(self) -> list[str]: ...

    def count(self, split: str) -> int: ...

    def iter_tasks(
        self, split: str, filters: dict[str, Any] | None = None
    ) -> Iterator[Task]: ...

    def get_task(self, task_id: str) -> Task: ...


def task(
    value: Any | None = None,
    *,
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Declare a task object/factory for eval autodiscovery."""

    if task_id is not None and (not isinstance(task_id, str) or not task_id.strip()):
        raise SnowlValidationError("Decorator @task(...): 'task_id' must be a non-empty string.")

    def _decorate(inner: Any) -> Any:
        declared_id = task_id.strip() if isinstance(task_id, str) and task_id.strip() else None
        if isinstance(inner, Task) and declared_id and inner.task_id != declared_id:
            inner = Task(
                task_id=declared_id,
                env_spec=inner.env_spec,
                sample_iter_factory=inner.sample_iter_factory,
                metadata=dict(inner.metadata),
            )
        return declare(inner, kind="task", object_id=declared_id, metadata=metadata)

    if value is not None:
        return _decorate(value)
    return _decorate


def validate_task(task: Task) -> None:
    """Validate a task with actionable error messages."""

    if not isinstance(task.task_id, str) or not task.task_id.strip():
        raise SnowlValidationError("Task.task_id must be a non-empty string.")

    if not isinstance(task.env_spec, EnvSpec):
        raise SnowlValidationError(
            "Task.env_spec must be an EnvSpec instance."
        )

    if not isinstance(task.env_spec.env_type, str) or not task.env_spec.env_type.strip():
        raise SnowlValidationError("EnvSpec.env_type must be a non-empty string.")
    validate_env_spec(task.env_spec)

    if not callable(task.sample_iter_factory):
        raise SnowlValidationError(
            "Task.sample_iter_factory must be callable and return an iterator."
        )

    iterator = task.sample_iter_factory()
    if not hasattr(iterator, "__iter__"):
        raise SnowlValidationError(
            "Task.sample_iter_factory must return an iterator of samples."
        )


def validate_task_provider(provider: TaskProvider) -> None:
    """Validate that provider implements required protocol semantics."""

    missing: list[str] = []
    for method in ("list_splits", "count", "iter_tasks", "get_task"):
        if not hasattr(provider, method) or not callable(getattr(provider, method)):
            missing.append(method)

    if missing:
        raise SnowlValidationError(
            f"TaskProvider missing required methods: {', '.join(missing)}"
        )
