from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile


FORBIDDEN_MARKERS = (
    "node_modules/",
    ".snowl/",
    ".next/cache/",
    "__pycache__/",
    ".tsbuildinfo",
)


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, check=True)


def _archive_members(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as zf:
            return zf.namelist()
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as tf:
            return tf.getnames()
    raise ValueError(f"unsupported artifact: {path}")


def _assert_clean_artifact(path: Path) -> None:
    bad: list[str] = []
    for name in _archive_members(path):
        normalized = name.replace("\\", "/")
        if any(marker in normalized for marker in FORBIDDEN_MARKERS):
            bad.append(normalized)
    if bad:
        preview = "\n".join(f"  - {item}" for item in bad[:20])
        raise AssertionError(f"{path.name} contains forbidden package paths:\n{preview}")


def _find_artifacts(dist_dir: Path) -> tuple[Path, Path]:
    wheels = sorted(dist_dir.glob("snowl-*.whl"))
    sdists = sorted(dist_dir.glob("snowl-*.tar.gz"))
    if not wheels:
        raise FileNotFoundError(f"no snowl wheel found in {dist_dir}")
    if not sdists:
        raise FileNotFoundError(f"no snowl sdist found in {dist_dir}")
    return wheels[-1], sdists[-1]


def _venv_python(root: Path) -> Path:
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return root / bin_dir / exe


def _venv_script(root: Path, name: str) -> Path:
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    return root / bin_dir / f"{name}{suffix}"


def run_package_smoke(dist_dir: Path) -> None:
    wheel, sdist = _find_artifacts(dist_dir)
    _assert_clean_artifact(wheel)
    _assert_clean_artifact(sdist)

    with tempfile.TemporaryDirectory(prefix="snowl-package-smoke-") as tmp:
        venv_dir = Path(tmp) / "venv"
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = _venv_python(venv_dir)
        snowl = _venv_script(venv_dir, "snowl")
        env = {**os.environ, "SNOWL_WEBUI_SOURCE": "bundled"}

        _run([str(python), "-m", "pip", "install", "--disable-pip-version-check", str(wheel)])
        _run([str(python), "-c", "import snowl; print(snowl.__version__)"], env=env)
        _run([str(snowl), "--help"], env=env)
        _run([str(snowl), "bench", "list"], env=env)
        _run([str(snowl), "bench", "check", "strongreject"], env=env)

    print(f"package smoke passed for {wheel.name} and {sdist.name}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Snowl package artifacts and installed CLI behavior.")
    parser.add_argument("--dist-dir", default="dist", help="Directory containing snowl wheel and sdist artifacts.")
    args = parser.parse_args()
    dist_dir = Path(args.dist_dir).resolve()
    if shutil.which("python") is None:
        raise RuntimeError("python executable not found")
    run_package_smoke(dist_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
