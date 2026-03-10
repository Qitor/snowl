"""Next.js runtime bootstrap for Snowl Web monitor."""

from __future__ import annotations

import hashlib
from importlib import metadata as importlib_metadata
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable


class WebRuntimeError(RuntimeError):
    """Raised when the embedded Next.js runtime cannot be bootstrapped."""


class NextWebRuntime:
    """Prepared Next.js runtime location."""

    def __init__(self, *, app_dir: Path, cache_key: str, source_dir: Path, source_mode: str) -> None:
        self.app_dir = app_dir
        self.cache_key = cache_key
        self.source_dir = source_dir
        self.source_mode = source_mode


def _snowl_version() -> str:
    try:
        return importlib_metadata.version("snowl")
    except Exception:
        return "0.0.0-dev"


def _bundled_webui_dir() -> Path:
    return (Path(__file__).resolve().parent.parent / "_webui").resolve()


def _repo_webui_dir() -> Path:
    return (Path(__file__).resolve().parents[2] / "webui").resolve()


def _has_webui_manifest(path: Path) -> bool:
    return (path / "package.json").exists()


def resolve_webui_source() -> tuple[Path, str]:
    """Resolve webui source directory and the selected source mode."""
    prefer = os.getenv("SNOWL_WEBUI_SOURCE", "auto").strip().lower()
    if prefer not in {"auto", "repo", "bundled"}:
        prefer = "auto"

    bundled = _bundled_webui_dir()
    repo_fallback = _repo_webui_dir()
    repo_root = repo_fallback.parent
    repo_ready = _has_webui_manifest(repo_fallback)
    bundled_ready = _has_webui_manifest(bundled)
    repo_like = repo_ready and (repo_root / "pyproject.toml").exists() and (repo_root / "snowl").is_dir()

    if prefer == "repo":
        if repo_ready:
            return repo_fallback, "repo"
        raise WebRuntimeError(f"requested SNOWL_WEBUI_SOURCE=repo but source is missing: {repo_fallback}")

    if prefer == "bundled":
        if bundled_ready:
            return bundled, "bundled"
        raise WebRuntimeError(f"requested SNOWL_WEBUI_SOURCE=bundled but source is missing: {bundled}")

    # auto mode: in editable/dev repo, always prefer repo root webui.
    if repo_like:
        return repo_fallback, "repo"
    if bundled_ready:
        return bundled, "bundled"
    if repo_ready:
        return repo_fallback, "repo"
    raise WebRuntimeError("built-in webui source is missing (package.json not found).")


def resolve_webui_source_dir() -> Path:
    """Compatibility helper returning only the source path."""
    source_dir, _source_mode = resolve_webui_source()
    return source_dir


def _lock_hash(source_dir: Path) -> str:
    lock_path = source_dir / "package-lock.json"
    if lock_path.exists():
        content = lock_path.read_bytes()
    else:
        pkg_path = source_dir / "package.json"
        if not pkg_path.exists():
            raise WebRuntimeError(f"webui package metadata missing: {pkg_path}")
        content = pkg_path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def _source_hash(source_dir: Path) -> str:
    hasher = hashlib.sha256()
    files: list[Path] = []
    for root, dirnames, filenames in os.walk(source_dir):
        dirnames[:] = sorted([d for d in dirnames if d not in {"node_modules", ".next", ".git"}])
        for filename in sorted(filenames):
            files.append(Path(root) / filename)
    for path in files:
        rel = path.relative_to(source_dir).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        try:
            hasher.update(path.read_bytes())
        except Exception:
            hasher.update(b"<read-error>")
        hasher.update(b"\0")
    return hasher.hexdigest()


def _cache_key(*, source_dir: Path) -> str:
    lock_part = _lock_hash(source_dir=source_dir)[:12]
    src_part = _source_hash(source_dir=source_dir)[:12]
    return f"{_snowl_version()}-{lock_part}-{src_part}"


def current_webui_cache_key() -> str:
    source_dir, _source_mode = resolve_webui_source()
    return _cache_key(source_dir=source_dir)


def _ensure_node_available() -> None:
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")
    if node_path is None or npm_path is None:
        raise WebRuntimeError("Node.js + npm are required. Install Node LTS (>=18).")
    try:
        result = subprocess.run(
            [node_path, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        raise WebRuntimeError("failed to execute `node --version`.") from exc
    version_text = (result.stdout or result.stderr or "").strip()
    m = re.search(r"v?(\d+)\.", version_text)
    if not m:
        raise WebRuntimeError(f"unable to parse Node.js version from: {version_text or '(empty)'}")
    major = int(m.group(1))
    if major < 18:
        raise WebRuntimeError(f"Node.js >=18 is required, found: {version_text}")


def ensure_next_runtime(*, log: Callable[[str], None] | None = None) -> NextWebRuntime:
    logger = log or (lambda _msg: None)
    _ensure_node_available()
    source_dir, source_mode = resolve_webui_source()
    app_dir = source_dir
    cache_key = _cache_key(source_dir=app_dir)
    if not (app_dir / "package.json").exists():
        raise WebRuntimeError(f"webui package metadata missing: {app_dir / 'package.json'}")

    lock_hash = _lock_hash(source_dir=app_dir)
    deps_stamp = app_dir / ".deps-lock.sha256"
    deps_ready = (app_dir / "node_modules").exists() and deps_stamp.exists() and deps_stamp.read_text(encoding="utf-8").strip() == lock_hash
    if not deps_ready:
        logger("[web] ensure deps: npm ci")
        subprocess.run(["npm", "ci"], cwd=str(app_dir), check=True)
        deps_stamp.write_text(lock_hash, encoding="utf-8")
    else:
        logger("[web] ensure deps: reuse")

    return NextWebRuntime(app_dir=app_dir, cache_key=cache_key, source_dir=source_dir, source_mode=source_mode)


def ensure_next_build(runtime: NextWebRuntime, *, log: Callable[[str], None] | None = None) -> None:
    logger = log or (lambda _msg: None)
    build_id = runtime.app_dir / ".next" / "BUILD_ID"
    stamp_path = runtime.app_dir / ".next" / ".snowl-build-stamp"
    expected_stamp = runtime.cache_key
    needs_build = True
    if build_id.exists() and stamp_path.exists():
        current_stamp = stamp_path.read_text(encoding="utf-8").strip()
        if current_stamp == expected_stamp:
            needs_build = False
    if not needs_build:
        logger("[web] ensure build: reuse")
        return
    logger("[web] ensure build: npm run build (source changed or missing build)")
    subprocess.run(["npm", "run", "build"], cwd=str(runtime.app_dir), check=True)
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(expected_stamp, encoding="utf-8")
