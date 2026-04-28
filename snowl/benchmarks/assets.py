"""Pinned benchmark asset loading helpers.

Framework role:
- Provides small, explicit download/cache helpers for benchmark adapters that
  depend on remote datasets.
- Keeps benchmark assets pinned by revision/checksum instead of accepting
  floating upstream refs.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests

from snowl.errors import SnowlValidationError


def benchmark_cache_root() -> Path:
    raw = os.getenv("SNOWL_BENCHMARK_CACHE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / ".snowl" / "cache" / "benchmarks"


def stable_benchmark_id(prefix: str, *parts: object) -> str:
    text = "\n".join(str(part) for part in parts if part is not None)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    clean_prefix = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in prefix).strip("-_")
    return f"{clean_prefix or 'sample'}-{digest}"


def _require_pinned_revision(source: str, revision: str | None) -> str:
    rev = str(revision or "").strip()
    if not rev:
        raise SnowlValidationError(
            f"Benchmark asset '{source}' must declare a pinned revision."
        )
    return rev


def _missing_dependency(package: str, extra: str = "safety_assets") -> SnowlValidationError:
    return SnowlValidationError(
        f"Missing optional dependency '{package}'. Install Snowl with the "
        f"'{extra}' extra to use remote benchmark assets."
    )


@dataclass(frozen=True)
class HFDatasetAsset:
    source: str
    revision: str
    split: str
    name: str | None = None
    cache_tag: str | None = None

    def load_rows(self) -> list[dict[str, Any]]:
        revision = _require_pinned_revision(self.source, self.revision)
        try:
            from datasets import load_dataset  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency-specific
            raise _missing_dependency("datasets<4.7.0") from exc

        cache_dir = benchmark_cache_root() / "hf_dataset" / (self.cache_tag or self.source.replace("/", "__"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, Any] = {
            "path": self.source,
            "split": self.split,
            "revision": revision,
            "cache_dir": str(cache_dir),
        }
        if self.name:
            kwargs["name"] = self.name
        dataset = load_dataset(**kwargs)
        return _rows_from_iterable(dataset)


@dataclass(frozen=True)
class HFSnapshotFileAsset:
    source: str
    revision: str
    relative_path: str
    allow_patterns: tuple[str, ...] = ("**/*",)
    cache_tag: str | None = None

    def resolve_path(self) -> Path:
        revision = _require_pinned_revision(self.source, self.revision)
        try:
            from huggingface_hub import snapshot_download  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency-specific
            raise _missing_dependency("huggingface_hub>=0.24") from exc

        local_dir = benchmark_cache_root() / "hf_snapshot" / (self.cache_tag or self.source.replace("/", "__"))
        local_dir.mkdir(parents=True, exist_ok=True)
        root = snapshot_download(
            repo_id=self.source,
            repo_type="dataset",
            revision=revision,
            local_dir=str(local_dir),
            allow_patterns=list(self.allow_patterns),
        )
        path = Path(root) / self.relative_path
        if not path.exists():
            raise SnowlValidationError(f"Snapshot asset file not found: {path}")
        return path


@dataclass(frozen=True)
class DirectURLAsset:
    url: str
    sha256: str
    cache_name: str

    def resolve_path(self) -> Path:
        expected = str(self.sha256 or "").strip().lower()
        if not expected:
            raise SnowlValidationError(f"Direct URL asset must declare sha256: {self.url}")
        out = benchmark_cache_root() / "direct_url" / self.cache_name
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and _sha256(out) == expected:
            return out
        resp = requests.get(self.url, timeout=60)
        resp.raise_for_status()
        out.write_bytes(resp.content)
        actual = _sha256(out)
        if actual != expected:
            try:
                out.unlink()
            except OSError:
                pass
            raise SnowlValidationError(
                f"Checksum mismatch for {self.url}: expected {expected}, got {actual}"
            )
        return out


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _rows_from_iterable(dataset: Iterable[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in dataset:
        if isinstance(item, dict):
            rows.append(dict(item))
        elif isinstance(item, str):
            try:
                parsed = json.loads(item)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(dict(parsed))
    return rows
