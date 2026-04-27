"""Internal normalized eval specification.

The v1 user-facing ``project.yml`` contract remains unchanged. ``EvalSpec`` is
an internal transition model used by the control plane so later work can add
new authoring surfaces without forcing more responsibilities into
``snowl.eval``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from snowl.project_config import ProjectCodeConfig, ProjectConfig


@dataclass(frozen=True)
class EvalSpec:
    """Normalized internal eval entry contract.

    ``EvalSpec`` adapts current project.yml and legacy-directory entrypoints
    into one control-plane shape. It is deliberately internal and does not
    define a public YAML/API version.
    """

    entry_path: Path
    base_dir: Path
    benchmark: str
    source_kind: str = "eval"
    code_config: ProjectCodeConfig | None = None
    project_config: ProjectConfig | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_project(
        cls,
        *,
        entry_path: Path,
        project_config: ProjectConfig,
        source_kind: str = "eval",
        source_metadata: dict[str, Any] | None = None,
    ) -> "EvalSpec":
        return cls(
            entry_path=entry_path,
            base_dir=project_config.root_dir,
            benchmark=project_config.eval.benchmark,
            source_kind=source_kind,
            code_config=project_config.eval.code,
            project_config=project_config,
            source_metadata=dict(source_metadata or {}),
        )

    @classmethod
    def from_legacy(
        cls,
        *,
        entry_path: Path,
        base_dir: Path,
        benchmark: str = "custom",
        source_kind: str = "eval",
        source_metadata: dict[str, Any] | None = None,
    ) -> "EvalSpec":
        return cls(
            entry_path=entry_path,
            base_dir=base_dir,
            benchmark=benchmark,
            source_kind=source_kind,
            source_metadata=dict(source_metadata or {}),
        )
