"""Tests for benchmark manifest validation and loading."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from snowl.benchmarks.manifest import (
    SCHEMA_VERSION,
    BenchmarkManifest,
    load_manifest,
    validate_manifest,
)
from snowl.errors import SnowlValidationError


def _valid_manifest_dict(**overrides) -> dict:
    base = {
        "schema_version": SCHEMA_VERSION,
        "name": "test_bench",
        "display_name": "Test Benchmark",
        "benchmark_type": "capability",
        "primary_metric": "accuracy",
        "source": {"paper": None, "code": None, "license": "MIT"},
        "adapter": {"entrypoint": "test_pkg.adapter:adapter"},
        "runtime": {"requires_docker": False},
        "scoring": {"method": "exact"},
    }
    base.update(overrides)
    return base


def test_valid_manifest_loads() -> None:
    data = _valid_manifest_dict()
    warnings = validate_manifest(data)
    assert isinstance(warnings, list)
    manifest = BenchmarkManifest.from_dict(data)
    assert manifest.name == "test_bench"
    assert manifest.schema_version == SCHEMA_VERSION


def test_missing_required_field_fails() -> None:
    for field in ("schema_version", "name", "display_name", "benchmark_type", "primary_metric", "source", "adapter", "runtime", "scoring"):
        data = _valid_manifest_dict()
        del data[field]
        with pytest.raises(SnowlValidationError, match="missing required"):
            validate_manifest(data)


def test_unknown_schema_version_fails() -> None:
    data = _valid_manifest_dict(schema_version="snowl.benchmark_manifest.v99")
    with pytest.raises(SnowlValidationError, match="Unsupported schema_version"):
        validate_manifest(data)


def test_invalid_benchmark_type_fails() -> None:
    data = _valid_manifest_dict(benchmark_type="invalid_type")
    with pytest.raises(SnowlValidationError, match="benchmark_type"):
        validate_manifest(data)


def test_invalid_name_format_fails() -> None:
    data = _valid_manifest_dict(name="Invalid-Name")
    with pytest.raises(SnowlValidationError, match="snake_case"):
        validate_manifest(data)


def test_missing_adapter_entrypoint_fails() -> None:
    data = _valid_manifest_dict(adapter={})
    with pytest.raises(SnowlValidationError, match="entrypoint"):
        validate_manifest(data)


def test_source_not_dict_fails() -> None:
    data = _valid_manifest_dict(source="not a dict")
    with pytest.raises(SnowlValidationError, match="source"):
        validate_manifest(data)


def test_manifest_from_yaml_file(tmp_path: Path) -> None:
    yaml_file = tmp_path / "benchmark.yaml"
    yaml_file.write_text(
        textwrap.dedent(
            f"""\
            schema_version: {SCHEMA_VERSION}
            name: my_bench
            display_name: My Benchmark
            benchmark_type: safety
            primary_metric: my_score
            source:
              license: Apache-2.0
            adapter:
              entrypoint: my_pkg:adapter
            runtime:
              requires_docker: true
            scoring:
              method: model_judge
            """
        ),
        encoding="utf-8",
    )
    manifest = load_manifest(yaml_file)
    assert manifest.name == "my_bench"
    assert manifest.benchmark_type == "safety"
    assert manifest.runtime.get("requires_docker") is True


def test_manifest_from_dict_roundtrip() -> None:
    data = _valid_manifest_dict()
    manifest = BenchmarkManifest.from_dict(data)
    exported = manifest.to_dict()
    assert exported["name"] == "test_bench"
    assert exported["schema_version"] == SCHEMA_VERSION


def test_non_dict_input_fails() -> None:
    with pytest.raises(SnowlValidationError, match="must be a dict"):
        validate_manifest("not a dict")


def test_warnings_for_missing_optional_fields() -> None:
    data = _valid_manifest_dict()
    # Remove optional fields that generate warnings
    data.pop("data", None)
    data.pop("reproducibility", None)
    data["source"].pop("license", None)
    warnings = validate_manifest(data)
    assert any("license" in w for w in warnings)
    assert any("data" in w for w in warnings)
    assert any("reproducibility" in w for w in warnings)


def test_manifest_status_default() -> None:
    manifest = BenchmarkManifest.from_dict(_valid_manifest_dict())
    assert manifest.status == "stable"


def test_strongreject_manifest_loads_and_matches_registry() -> None:
    """Reference benchmark: strongreject manifest loads and name matches registry entry."""
    from snowl.benchmarks.registry import get_default_benchmark_registry

    manifest = load_manifest(Path(__file__).parent.parent / "snowl" / "benchmarks" / "strongreject" / "benchmark.yaml")
    assert manifest.name == "strongreject"
    assert manifest.benchmark_type == "safety"

    registry = get_default_benchmark_registry()
    assert registry.has("strongreject")


def test_jsonl_manifest_loads_and_matches_registry() -> None:
    """Reference adapter: jsonl manifest loads and name matches registry entry."""
    from snowl.benchmarks.registry import get_default_benchmark_registry

    manifest = load_manifest(Path(__file__).parent.parent / "snowl" / "benchmarks" / "jsonl_adapter.yaml")
    assert manifest.name == "jsonl"

    registry = get_default_benchmark_registry()
    assert registry.has("jsonl")
