"""Tests for snowl-evals benchmark manifests."""
from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.manifest import load_manifest


EVALS_ROOT = Path(__file__).resolve().parents[1] / "snowl_evals"


def test_strongreject_manifest_valid() -> None:
    manifest = load_manifest(EVALS_ROOT / "strongreject" / "benchmark.yaml")
    assert manifest.name == "strongreject"
    assert manifest.benchmark_type == "safety"


def test_xstest_manifest_valid() -> None:
    manifest = load_manifest(EVALS_ROOT / "xstest" / "benchmark.yaml")
    assert manifest.name == "xstest"


def test_wmdp_manifest_valid() -> None:
    manifest = load_manifest(EVALS_ROOT / "wmdp" / "benchmark.yaml")
    assert manifest.name == "wmdp"


def test_sec_qa_manifest_valid() -> None:
    manifest = load_manifest(EVALS_ROOT / "sec_qa" / "benchmark.yaml")
    assert manifest.name == "sec_qa"


def test_cybermetric_manifest_valid() -> None:
    manifest = load_manifest(EVALS_ROOT / "cybermetric" / "benchmark.yaml")
    assert manifest.name == "cybermetric"
