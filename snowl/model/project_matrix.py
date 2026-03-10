"""Compatibility wrappers around the unified project.yml loader."""

from __future__ import annotations

from pathlib import Path

from snowl.project_config import (
    ProjectConfig,
    ProjectJudgeConfig,
    ProjectModelEntry,
    ProjectProviderConfig,
    load_project_config,
)


ProjectModelMatrix = ProjectConfig


def load_project_model_matrix(base_dir: str | Path) -> ProjectConfig:
    return load_project_config(base_dir)


def apply_project_judge_env(base_dir: str | Path) -> dict[str, str]:
    _ = base_dir
    return {}
