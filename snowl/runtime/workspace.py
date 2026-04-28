"""Runtime-owned per-trial workspace materialization and snapshots."""

from __future__ import annotations

import hashlib
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(k): v for k, v in value.items()}
    return {}


def _safe_part(value: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in str(value or ""))
    return out.strip("-") or "workspace"


@dataclass(frozen=True)
class RuntimeWorkspaceSpec:
    enabled: bool = False
    root: str | None = None
    source_dir: str | None = None
    repo_files: dict[str, Any] = field(default_factory=dict)
    seed_files: dict[str, Any] = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()
    preserve: bool = False

    def to_metadata(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "root": self.root,
            "source_dir": self.source_dir,
            "repo_file_count": len(self.repo_files),
            "seed_file_count": len(self.seed_files),
            "artifacts": list(self.artifacts),
            "preserve": self.preserve,
        }


@dataclass(frozen=True)
class RuntimeWorkspaceSession:
    workspace_dir: str
    before: dict[str, str]
    spec: RuntimeWorkspaceSpec


def resolve_workspace_spec(
    *,
    task_metadata: Mapping[str, Any] | None,
    sample: Mapping[str, Any] | None,
    container_startup: Mapping[str, Any] | None = None,
    container_workspace: Mapping[str, Any] | None = None,
) -> RuntimeWorkspaceSpec:
    task_meta = _as_mapping(task_metadata)
    sample_row = _as_mapping(sample)
    sample_meta = _as_mapping(sample_row.get("metadata"))
    startup = _as_mapping(container_startup)

    task_workspace = _as_mapping(task_meta.get("workspace"))
    sample_workspace = _as_mapping(sample_meta.get("workspace"))
    contract_workspace = _as_mapping(container_workspace)
    workspace = {**task_workspace, **contract_workspace, **sample_workspace}

    repo_files = _as_mapping(
        workspace.get("repo_files")
        or sample_meta.get("repo_files")
        or startup.get("repo_files")
    )
    seed_files = _as_mapping(workspace.get("seed_files") or startup.get("seed_files"))
    source_dir = workspace.get("source_dir") or startup.get("source_dir")
    enabled = bool(
        workspace.get("enabled", False)
        or repo_files
        or seed_files
        or source_dir
    )
    raw_artifacts = workspace.get("artifacts") or startup.get("artifacts") or ()
    if isinstance(raw_artifacts, str):
        artifacts = (raw_artifacts,)
    elif isinstance(raw_artifacts, (list, tuple)):
        artifacts = tuple(str(item) for item in raw_artifacts if str(item).strip())
    else:
        artifacts = ()
    return RuntimeWorkspaceSpec(
        enabled=enabled,
        root=(str(workspace.get("root")) if workspace.get("root") else None),
        source_dir=(str(source_dir) if source_dir else None),
        repo_files=repo_files,
        seed_files=seed_files,
        artifacts=artifacts,
        preserve=bool(workspace.get("preserve", False)),
    )


class RuntimeWorkspaceManager:
    def __init__(
        self,
        *,
        run_id: str | None,
        trial_id: str | None,
        task_id: str,
        sample_id: str | None,
        spec: RuntimeWorkspaceSpec,
    ) -> None:
        self.run_id = run_id
        self.trial_id = trial_id
        self.task_id = task_id
        self.sample_id = sample_id
        self.spec = spec

    def prepare(self) -> RuntimeWorkspaceSession | None:
        if not self.spec.enabled:
            return None
        workspace_dir = self._workspace_dir()
        if workspace_dir.exists() and not self.spec.preserve:
            shutil.rmtree(workspace_dir)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        if self.spec.source_dir:
            self._copy_source(Path(self.spec.source_dir), workspace_dir)
        self._write_files(workspace_dir, self.spec.repo_files)
        self._write_files(workspace_dir, self.spec.seed_files)
        before = snapshot_workspace(workspace_dir)
        return RuntimeWorkspaceSession(
            workspace_dir=str(workspace_dir),
            before=before,
            spec=self.spec,
        )

    def _workspace_dir(self) -> Path:
        if self.spec.root:
            root = Path(self.spec.root)
        else:
            root = Path.cwd() / ".snowl" / "workspaces"
        name_basis = "|".join(
            [
                str(self.run_id or "run"),
                str(self.trial_id or ""),
                str(self.task_id or ""),
                str(self.sample_id or ""),
            ]
        )
        digest = hashlib.sha1(name_basis.encode("utf-8")).hexdigest()[:10]
        return (
            root
            / _safe_part(str(self.run_id or "local"))
            / f"{_safe_part(str(self.sample_id or self.task_id))}-{digest}"
        ).resolve()

    def _copy_source(self, source: Path, target: Path) -> None:
        source = source.resolve()
        if not source.exists() or not source.is_dir():
            raise RuntimeError(f"workspace source_dir not found: {source}")
        for child in source.iterdir():
            dest = target / child.name
            if child.is_dir():
                shutil.copytree(child, dest, dirs_exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, dest)

    def _write_files(self, root: Path, files: Mapping[str, Any]) -> None:
        for rel_path, content in files.items():
            raw_rel = str(rel_path).strip()
            if not raw_rel or raw_rel.startswith("/") or ".." in Path(raw_rel).parts:
                raise RuntimeError(f"unsafe workspace file path: {raw_rel}")
            path = root / raw_rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(content), encoding="utf-8")


def snapshot_workspace(root: str | Path) -> dict[str, str]:
    root_path = Path(root)
    if not root_path.exists():
        return {}
    out: dict[str, str] = {}
    for path in sorted(p for p in root_path.rglob("*") if p.is_file()):
        rel = path.relative_to(root_path).as_posix()
        if rel.startswith(".snowl/"):
            continue
        try:
            out[rel] = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            out[rel] = f"<binary:{path.stat().st_size}:{int(path.stat().st_mtime)}>"
    return out


def diff_workspace(before: Mapping[str, str], after: Mapping[str, str]) -> dict[str, Any]:
    before_map = {str(k): str(v) for k, v in before.items()}
    after_map = {str(k): str(v) for k, v in after.items()}
    added = sorted(path for path in after_map if path not in before_map)
    modified = sorted(path for path in after_map if path in before_map and before_map[path] != after_map[path])
    deleted = sorted(path for path in before_map if path not in after_map)
    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "changed": sorted(added + modified),
        "file_count_before": len(before_map),
        "file_count_after": len(after_map),
        "snapshotted_at_ms": int(time.time() * 1000),
    }


__all__ = [
    "RuntimeWorkspaceManager",
    "RuntimeWorkspaceSession",
    "RuntimeWorkspaceSpec",
    "diff_workspace",
    "resolve_workspace_spec",
    "snapshot_workspace",
]
