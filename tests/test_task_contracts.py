from __future__ import annotations

import pytest

from snowl.core import EnvSpec, Task, TaskProvider, validate_task, validate_task_provider
from snowl.errors import SnowlValidationError


def test_validate_task_ok() -> None:
    task = Task(
        task_id="task-1",
        env_spec=EnvSpec(env_type="docker"),
        sample_iter_factory=lambda: iter([{"id": "s1"}]),
    )
    validate_task(task)


def test_validate_task_invalid_task_id() -> None:
    task = Task(
        task_id="",
        env_spec=EnvSpec(env_type="docker"),
        sample_iter_factory=lambda: iter([]),
    )
    with pytest.raises(SnowlValidationError, match="task_id"):
        validate_task(task)


def test_validate_task_invalid_env_type() -> None:
    task = Task(
        task_id="task-1",
        env_spec=EnvSpec(env_type=""),
        sample_iter_factory=lambda: iter([]),
    )
    with pytest.raises(SnowlValidationError, match="env_type"):
        validate_task(task)


class _GoodProvider:
    def list_splits(self) -> list[str]:
        return ["test"]

    def count(self, split: str) -> int:
        return 1

    def iter_tasks(self, split: str, filters=None):
        yield Task(
            task_id="task-1",
            env_spec=EnvSpec(env_type="docker"),
            sample_iter_factory=lambda: iter([]),
        )

    def get_task(self, task_id: str) -> Task:
        return Task(
            task_id=task_id,
            env_spec=EnvSpec(env_type="docker"),
            sample_iter_factory=lambda: iter([]),
        )


def test_validate_task_provider_ok() -> None:
    provider: TaskProvider = _GoodProvider()
    validate_task_provider(provider)


class _BadProvider:
    def list_splits(self) -> list[str]:
        return ["test"]


def test_validate_task_provider_missing_methods() -> None:
    with pytest.raises(SnowlValidationError, match="missing required methods"):
        validate_task_provider(_BadProvider())
