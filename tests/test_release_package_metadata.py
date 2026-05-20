from __future__ import annotations

import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from scripts.package_smoke import _assert_clean_artifact


ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_declares_apache_license() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE"]
    assert all("License ::" not in classifier for classifier in project["classifiers"])

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "license-Apache--2.0" in readme
    assert "Apache License 2.0" in readme

    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text


def test_package_exclusion_patterns_cover_runtime_caches() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    for expected in (
        "prune snowl/_webui/node_modules",
        "prune snowl/_webui/.snowl",
        "prune snowl/_webui/.next/cache",
        "global-exclude *.tsbuildinfo",
        "global-exclude *.py[cod]",
    ):
        assert expected in manifest

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    excluded = pyproject["tool"]["setuptools"]["exclude-package-data"]["snowl"]
    for expected in (
        "_webui/node_modules/**",
        "_webui/.snowl/**",
        "_webui/.next/cache/**",
        "_webui/**/*.tsbuildinfo",
    ):
        assert expected in excluded


def test_package_smoke_rejects_forbidden_wheel_paths(tmp_path: Path) -> None:
    wheel = tmp_path / "snowl-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("snowl/__init__.py", "")
        zf.writestr("snowl/_webui/node_modules/pkg/index.js", "")

    with pytest.raises(AssertionError, match="forbidden package paths"):
        _assert_clean_artifact(wheel)


def test_package_smoke_rejects_forbidden_sdist_paths(tmp_path: Path) -> None:
    payload = tmp_path / "artifact.pyc"
    payload.write_bytes(b"bad")
    sdist = tmp_path / "snowl-0.1.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as tf:
        tf.add(payload, arcname="snowl-0.1.0/examples/__pycache__/artifact.pyc")

    with pytest.raises(AssertionError, match="forbidden package paths"):
        _assert_clean_artifact(sdist)
