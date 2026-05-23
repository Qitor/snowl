"""Benchmark manifest loading and validation.

Framework role:
- Loads ``benchmark.yaml`` manifests that accompany each benchmark adapter.
- Provides structured access to manifest fields for CLI, docs, and conformance checks.

Runtime/usage wiring:
- Used by snowl-evals CI and conformance tests to validate manifests.
- Key top-level symbols: ``BenchmarkManifest``, ``load_manifest``.

Change guardrails:
- ``BenchmarkManifest`` field additions must be optional with defaults.
- Removal or renaming of existing fields is a breaking change for manifests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class BenchmarkManifest:
    """Structured representation of a ``benchmark.yaml`` manifest."""

    schema_version: str = ""
    name: str = ""
    display_name: str = ""
    family: str = ""
    domain: str = ""
    benchmark_type: str = ""
    primary_metric: str = ""
    higher_is_better: bool = True
    status: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    adapter: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    scoring: dict[str, Any] = field(default_factory=dict)
    reproducibility: dict[str, Any] = field(default_factory=dict)
    migration: dict[str, Any] = field(default_factory=dict)

    @property
    def entrypoint(self) -> str:
        return self.adapter.get("entrypoint", "")

    @property
    def env_type(self) -> str:
        return self.runtime.get("env_type", "local")

    @property
    def requires_network(self) -> bool:
        return self.runtime.get("requires_network", False)

    @property
    def requires_docker(self) -> bool:
        return self.runtime.get("requires_docker", False)

    @property
    def scoring_method(self) -> str:
        return self.scoring.get("method", "")


def load_manifest(path: str | Path) -> BenchmarkManifest:
    """Load and parse a ``benchmark.yaml`` manifest file.

    Parameters:
        path: Filesystem path to the YAML manifest.

    Returns:
        A ``BenchmarkManifest`` populated from the YAML content.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        ValueError: If the YAML content is not a mapping.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Manifest not found: {p}")
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"Manifest must be a YAML mapping, got {type(raw).__name__}")
    return BenchmarkManifest(
        schema_version=raw.get("schema_version", ""),
        name=raw.get("name", ""),
        display_name=raw.get("display_name", ""),
        family=raw.get("family", ""),
        domain=raw.get("domain", ""),
        benchmark_type=raw.get("benchmark_type", ""),
        primary_metric=raw.get("primary_metric", ""),
        higher_is_better=raw.get("higher_is_better", True),
        status=raw.get("status", ""),
        source=raw.get("source", {}),
        adapter=raw.get("adapter", {}),
        runtime=raw.get("runtime", {}),
        data=raw.get("data", {}),
        scoring=raw.get("scoring", {}),
        reproducibility=raw.get("reproducibility", {}),
        migration=raw.get("migration", {}),
    )
