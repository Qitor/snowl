from __future__ import annotations

import os
import shutil
import subprocess

import pytest


@pytest.mark.skipif(
    os.getenv("SNOWL_RUN_DOCKER_SMOKE", "").strip().lower() not in {"1", "true", "yes", "on"},
    reason="set SNOWL_RUN_DOCKER_SMOKE=1 to run the real Docker sandbox smoke",
)
@pytest.mark.skipif(shutil.which("docker") is None, reason="docker executable is not available")
def test_sandbox_coding_docker_smoke() -> None:
    subprocess.run(
        [
            "python",
            "-m",
            "snowl.cli",
            "eval",
            "examples/sandbox-coding-smoke/docker-project.yml",
            "--no-web-monitor",
        ],
        check=True,
    )
