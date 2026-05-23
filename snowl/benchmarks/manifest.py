"""Benchmark manifest loader and validator.

Provides a lightweight contract for benchmark adapters to declare metadata,
source attribution, runtime requirements, and scoring method. Manifests
follow the `snowl.benchmark_manifest.v1` schema.

Framework role:
- Validates benchmark manifests without heavyweight dependencies.
- Used by conformance checks and future snowl-evals packaging.

Runtime/usage wiring:
- ``load_manifest(path)`` reads a YAML file and validates it.
- ``validate_manifest(data)`` validates a dict in-process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from snowl.errors import SnowlValidationError

SCHEMA_VERSION = "snowl.benchmark_manifest.v1"

BENCHMARK_TYPES = ("capability", "safety", "tool_use", "knowledge", "reasoning", "other")

REQUIRED_TOP_LEVEL = (
    "schema_version",
    "name",
    "display_name",
    "benchmark_type",
    "primary_metric",
    "source",
    "adapter",
    "runtime",
    "scoring",
)

REQUIRED_ADAPTER_FIELDS = ("entrypoint",)


@dataclass(frozen=True)
class BenchmarkManifest:
    """Parsed and validated benchmark manifest."""

    schema_version: str
    name: str
    display_name: str
    benchmark_type: str
    primary_metric: str
    higher_is_better: bool = True
    status: str = "stable"
    family: str = ""
    domain: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    adapter: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    scoring: dict[str, Any] = field(default_factory=dict)
    reproducibility: dict[str, Any] = field(default_factory=dict)
    maintainers: list[dict[str, Any]] = field(default_factory=list)
    migration: dict[str, Any] = field(default_factory=dict)
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkManifest:
        validate_manifest(data)
        return cls(
            schema_version=data["schema_version"],
            name=data["name"],
            display_name=data["display_name"],
            benchmark_type=data["benchmark_type"],
            primary_metric=data["primary_metric"],
            higher_is_better=data.get("higher_is_better", True),
            status=data.get("status", "stable"),
            family=data.get("family", data["name"]),
            domain=data.get("domain", ""),
            source=dict(data.get("source") or {}),
            adapter=dict(data.get("adapter") or {}),
            runtime=dict(data.get("runtime") or {}),
            data=dict(data.get("data") or {}),
            scoring=dict(data.get("scoring") or {}),
            reproducibility=dict(data.get("reproducibility") or {}),
            maintainers=list(data.get("maintainers") or []),
            migration=dict(data.get("migration") or {}),
            _raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self._raw) if self._raw else {
            "schema_version": self.schema_version,
            "name": self.name,
            "display_name": self.display_name,
            "benchmark_type": self.benchmark_type,
            "primary_metric": self.primary_metric,
            "higher_is_better": self.higher_is_better,
            "status": self.status,
            "family": self.family,
            "domain": self.domain,
            "source": self.source,
            "adapter": self.adapter,
            "runtime": self.runtime,
            "data": self.data,
            "scoring": self.scoring,
            "reproducibility": self.reproducibility,
            "maintainers": self.maintainers,
            "migration": self.migration,
        }


def validate_manifest(data: dict[str, Any]) -> list[str]:
    """Validate a manifest dict. Raises SnowlValidationError on failure.

    Returns a list of warnings (non-fatal issues).
    """
    if not isinstance(data, dict):
        raise SnowlValidationError("Manifest must be a dict/mapping.")

    # Required top-level fields
    missing = [f for f in REQUIRED_TOP_LEVEL if f not in data]
    if missing:
        raise SnowlValidationError(
            f"Manifest missing required fields: {', '.join(missing)}"
        )

    # Schema version
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise SnowlValidationError(
            f"Unsupported schema_version '{version}'. Expected '{SCHEMA_VERSION}'."
        )

    # Name format
    name = data.get("name", "")
    if not name or not isinstance(name, str):
        raise SnowlValidationError("Manifest 'name' must be a non-empty string.")
    if not name[0].islower() or not all(c.isalnum() or c == "_" for c in name):
        raise SnowlValidationError(
            f"Manifest 'name' must be snake_case (lowercase alphanumeric + underscore). Got: '{name}'"
        )

    # Display name
    if not data.get("display_name"):
        raise SnowlValidationError("Manifest 'display_name' must be non-empty.")

    # Benchmark type
    btype = data.get("benchmark_type")
    if btype not in BENCHMARK_TYPES:
        raise SnowlValidationError(
            f"Manifest 'benchmark_type' must be one of {BENCHMARK_TYPES}. Got: '{btype}'"
        )

    # Primary metric
    if not data.get("primary_metric"):
        raise SnowlValidationError("Manifest 'primary_metric' must be non-empty.")

    # Source must be a dict
    source = data.get("source")
    if not isinstance(source, dict):
        raise SnowlValidationError("Manifest 'source' must be a mapping.")

    # Adapter must have entrypoint
    adapter = data.get("adapter")
    if not isinstance(adapter, dict):
        raise SnowlValidationError("Manifest 'adapter' must be a mapping.")
    missing_adapter = [f for f in REQUIRED_ADAPTER_FIELDS if f not in adapter]
    if missing_adapter:
        raise SnowlValidationError(
            f"Manifest 'adapter' missing required fields: {', '.join(missing_adapter)}"
        )

    # Runtime must be a dict
    runtime = data.get("runtime")
    if not isinstance(runtime, dict):
        raise SnowlValidationError("Manifest 'runtime' must be a mapping.")

    # Scoring must be a dict
    scoring = data.get("scoring")
    if not isinstance(scoring, dict):
        raise SnowlValidationError("Manifest 'scoring' must be a mapping.")

    # Warnings
    warnings: list[str] = []
    if not source.get("license"):
        warnings.append("Manifest 'source.license' is not set — consider adding license info.")
    if not data.get("data"):
        warnings.append("Manifest 'data' section is empty — consider documenting dataset availability.")
    if not data.get("reproducibility"):
        warnings.append("Manifest 'reproducibility' section is empty — consider adding reproducibility notes.")

    return warnings


def load_manifest(path: str | Path) -> BenchmarkManifest:
    """Load and validate a benchmark manifest from a YAML file."""
    from snowl.benchmarks.utils import read_yaml_mapping

    data = read_yaml_mapping(path)
    return BenchmarkManifest.from_dict(data)
