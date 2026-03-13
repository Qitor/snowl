"""Compatibility helpers that read project-level provider/model matrix config for agent-variant generation.

Framework role:
- Provides a focused API for modules that only need provider + model matrix views from `project.yml`.

Runtime/usage wiring:
- Consumed by built-in model-variant builder helpers.
- Key top-level symbols in this file: `load_project_model_matrix`, `apply_project_judge_env`.

Change guardrails:
- Keep compatibility behavior stable while project config evolves.
"""

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
